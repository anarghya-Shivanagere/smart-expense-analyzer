"""Streamlit UI for Smart Expense Analyzer with DB-backed datasets."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import SmartExpenseAgent, load_config
from src.categorizer import AVAILABLE_CATEGORIES
from src.database import (
    add_categories,
    apply_category_corrections,
    import_csv_to_dataset,
    init_db,
    load_anomaly_feedback,
    list_datasets,
    list_custom_categories,
    list_months,
    load_merchant_rules,
    load_transactions,
    save_anomaly_feedback,
    save_run_summary,
    upsert_merchant_rules,
)
from src.settings import get_database_ref


def get_category_options(db_ref: str | Path) -> list[str]:
    built_in = list(AVAILABLE_CATEGORIES)
    custom = [category for category in list_custom_categories(db_ref) if category not in built_in]
    return sorted(set(built_in + custom))


def build_anomaly_review_candidates(
    categorized_rows: list[dict[str, object]],
    anomalies: list[dict[str, object]],
    limit_borderline: int = 5,
) -> list[dict[str, object]]:
    anomaly_keys = {
        (str(row.get("date", row.get("Date", ""))), str(row.get("description", row.get("Description", ""))), float(row.get("amount", row.get("Amount", 0.0))))
        for row in anomalies
    }
    candidates: list[dict[str, object]] = []
    for row in anomalies:
        candidates.append(
            {
                "date": str(row.get("date", row.get("Date", ""))),
                "description": str(row.get("description", row.get("Description", ""))),
                "amount": float(row.get("amount", row.get("Amount", 0.0))),
                "category": str(row.get("category", "")),
                "reason": f"Flagged anomaly ({row.get('context', row.get('Context', 'global'))})",
                "default_feedback": "Anomaly",
            }
        )
    non_anomalies = [
        row for row in categorized_rows
        if (str(row["date"]), str(row["description"]), abs(float(row["amount"]))) not in anomaly_keys
    ]
    borderline = sorted(non_anomalies, key=lambda row: abs(float(row["amount"])), reverse=True)[:limit_borderline]
    for row in borderline:
        candidates.append(
            {
                "date": str(row["date"]),
                "description": str(row["description"]),
                "amount": abs(float(row["amount"])),
                "category": str(row["category"]),
                "reason": "High-value transaction close to anomaly territory",
                "default_feedback": "Normal",
            }
        )
    return candidates


def parse_category_breakdown(report: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    in_section = False
    for line in report.splitlines():
        if line.strip() == "Category Breakdown:":
            in_section = True
            continue
        if in_section:
            if not line.strip() or line.startswith("Baseline Comparison"):
                break
            match = re.match(r"^\-\s+(.+?)\s+([0-9]+\.[0-9]+)$", line.strip())
            if match:
                rows.append({"Category": match.group(1).strip(), "Amount": float(match.group(2))})
    return rows


def parse_anomalies(report: str) -> list[dict[str, object]]:
    anomalies: list[dict[str, object]] = []
    in_section = False
    for line in report.splitlines():
        if line.strip() == "Anomalies:":
            in_section = True
            continue
        if in_section and line.strip().startswith("-"):
            parts = [p.strip() for p in line.strip()[1:].split("|")]
            if len(parts) >= 4:
                anomalies.append(
                    {
                        "Date": parts[0],
                        "Description": parts[1],
                        "Amount": parts[2],
                        "Z-Score": parts[3].replace("z=", ""),
                        "Context": parts[4] if len(parts) > 4 else "",
                    }
                )
    return anomalies


def build_tool_trace_rows(log_path: Path) -> list[dict[str, object]]:
    if not log_path.exists():
        return []
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    trace_rows: list[dict[str, object]] = []
    for row in rows:
        if row.get("event_type") not in {"tool_call", "tool_result"}:
            continue
        payload = row.get("payload", {})
        trace_rows.append(
            {
                "timestamp": row.get("timestamp", ""),
                "event_type": row.get("event_type", ""),
                "tool": payload.get("tool", ""),
                "details": json.dumps({k: v for k, v in payload.items() if k != "tool"}),
            }
        )
    return trace_rows


def bootstrap_sample_dataset(db_ref: str | Path) -> None:
    if "sample" in list_datasets(db_ref):
        return
    sample_csv = PROJECT_ROOT / "data" / "sample_transactions.csv"
    import_csv_to_dataset(db_ref, sample_csv, "sample")


def kpi_card(title: str, value: str, tone: str = "blue") -> None:
    st.markdown(
        f"""
        <div class="kpi {tone}">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_tile(title: str, text: str) -> None:
    st.markdown(
        f"""
        <div class="info-tile">
            <div class="info-tile-title">{title}</div>
            <div class="info-tile-text">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Smart Expense Analyzer", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Manrope:wght@500;600;700&display=swap');

    :root {
        --bg-a: #f7f4ee;
        --bg-b: #eef2f7;
        --ink: #182538;
        --muted: #5c6b7c;
        --line: #d7dfeb;
        --panel: rgba(255, 255, 255, 0.96);
        --panel-strong: #ffffff;
        --hero-a: #17324d;
        --hero-b: #245a7a;
        --hero-c: #d97f4a;
        --primary: #173f6b;
        --primary-2: #2d5f88;
        --accent: #d97f4a;
        --success: #dff5e8;
    }

    .stApp {
        background:
          radial-gradient(circle at 0% 0%, rgba(217,127,74,.12), transparent 24%),
          radial-gradient(circle at 100% 10%, rgba(36,90,122,.10), transparent 28%),
          linear-gradient(180deg, var(--bg-a) 0%, var(--bg-b) 100%);
        color: var(--ink);
    }

    h1,h2,h3,h4 {
        font-family: "Outfit", "Segoe UI", sans-serif;
        letter-spacing: -0.01em;
        color: var(--ink);
    }

    p, span, label, .stMarkdown, .stText, .stCaption {
        font-family: "Manrope", "Segoe UI", sans-serif;
        color: var(--ink);
    }

    .block-container {
        max-width: 1220px;
        padding-top: 1.25rem;
        padding-bottom: 2rem;
    }

    .stCaption {
        color: var(--muted) !important;
    }

    [data-testid="stFileUploader"],
    [data-testid="stNumberInputContainer"],
    [data-testid="stSelectbox"],
    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    [data-testid="stExpander"],
    div[data-testid="stCodeBlock"] {
        background: var(--panel);
        border: 1px solid rgba(24, 37, 56, 0.08);
        border-radius: 18px;
        box-shadow: 0 10px 30px rgba(24, 37, 56, 0.07);
    }

    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-baseweb="base-input"] > div {
        background: var(--panel-strong) !important;
        color: var(--ink) !important;
        border: 1px solid var(--line) !important;
        min-height: 58px;
        border-radius: 14px !important;
        box-shadow: none !important;
    }

    [data-baseweb="select"] input,
    [data-baseweb="input"] input,
    [data-baseweb="base-input"] input {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
    }

    [data-baseweb="select"] svg,
    [data-baseweb="input"] svg {
        fill: var(--muted) !important;
    }

    .hero {
        border-radius: 26px;
        background:
          radial-gradient(circle at 14% 24%, rgba(255,255,255,.10), transparent 20%),
          radial-gradient(circle at 88% 15%, rgba(255,255,255,.12), transparent 22%),
          linear-gradient(120deg, var(--hero-a) 0%, var(--hero-b) 54%, var(--hero-c) 100%);
        color: #f8fafc;
        padding: 26px 28px;
        margin-bottom: 18px;
        box-shadow: 0 18px 42px rgba(23, 50, 77, 0.18);
        border: 1px solid rgba(255,255,255,0.16);
    }

    .hero-title {
        margin: 0;
        font-size: 2.7rem;
        font-weight: 800;
        line-height: 1;
        color: #f8fafc !important;
    }

    .hero-sub {
        margin-top: 10px;
        opacity: 0.94;
        max-width: 760px;
        line-height: 1.45;
        font-size: 1.02rem;
        color: rgba(248,250,252,0.92) !important;
    }

    .chip {
        display:inline-block;
        border-radius:999px;
        border:1px solid rgba(255,255,255,.18);
        background:rgba(255,255,255,.14);
        color:#f8fafc;
        font-size:.8rem;
        font-weight: 700;
        padding: 5px 12px;
        margin-right: 6px;
        margin-top: 12px;
        backdrop-filter: blur(2px);
    }

    .kpi {
        border-radius: 20px;
        padding: 16px 16px;
        margin-bottom: 8px;
        border: 1px solid rgba(24,37,56,.08);
        box-shadow: 0 12px 24px rgba(24,37,56,0.08);
    }

    .kpi-title {
        font-size: .74rem;
        text-transform: uppercase;
        letter-spacing: .08em;
        color: #64748b;
        margin-bottom: 4px;
    }

    .kpi-value {
        font-size: 1.34rem;
        font-weight: 800;
        color: #0f172a;
        font-family: "Outfit", "Segoe UI", sans-serif;
    }

    .kpi.blue { background: linear-gradient(145deg, #dcebf8 0%, #f4f8fc 100%); }
    .kpi.cyan { background: linear-gradient(145deg, #ddeeea 0%, #f5fbf8 100%); }
    .kpi.amber { background: linear-gradient(145deg, #f7e4d6 0%, #fcf5ef 100%); }
    .kpi.rose { background: linear-gradient(145deg, #f0e4dc 0%, #fbf7f3 100%); }

    .info-tile {
        background: var(--panel);
        border: 1px solid rgba(24,37,56,.08);
        border-radius: 20px;
        padding: 18px 18px;
        min-height: 112px;
        box-shadow: 0 10px 30px rgba(24,37,56,0.06);
    }

    .info-tile-title {
        font-family: "Outfit", "Segoe UI", sans-serif;
        font-size: 1rem;
        font-weight: 700;
        color: var(--primary);
        margin-bottom: 6px;
    }

    .info-tile-text {
        color: var(--muted);
        line-height: 1.5;
        font-size: 0.94rem;
    }

    [data-testid="stButton"] button,
    [data-testid="stDownloadButton"] button,
    [data-testid="stFileUploader"] button {
        background: linear-gradient(135deg, var(--primary) 0%, var(--primary-2) 100%) !important;
        color: #f8fafc !important;
        border: 0 !important;
        border-radius: 14px !important;
        font-weight: 700 !important;
        min-height: 56px;
        box-shadow: 0 12px 24px rgba(23, 63, 107, 0.18);
    }

    [data-testid="stButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover,
    [data-testid="stFileUploader"] button:hover {
        filter: brightness(1.03);
        transform: translateY(-1px);
    }

    [data-testid="stButton"] button p,
    [data-testid="stDownloadButton"] button p,
    [data-testid="stFileUploader"] button p,
    [data-testid="stButton"] button span,
    [data-testid="stDownloadButton"] button span,
    [data-testid="stFileUploader"] button span {
        color: #f8fafc !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(255,255,255,0.70);
        padding: 6px;
        border-radius: 16px;
        border: 1px solid rgba(24,37,56,0.08);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        border: 1px solid transparent;
        background: transparent;
        padding: 10px 16px;
        color: var(--ink) !important;
        font-weight: 700;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #173f6b 0%, #2d5f88 100%) !important;
        color: #fff !important;
        border-color: transparent !important;
    }

    .stTabs [data-baseweb="tab"] p {
        color: inherit !important;
    }

    [data-testid="stAlert"] {
        border-radius: 18px;
        border: 1px solid rgba(24,37,56,0.08);
    }

    [data-testid="stAlert"] * {
        color: inherit !important;
    }

    [data-testid="stDataFrame"] *,
    [data-testid="stTable"] *,
    div[data-testid="stCodeBlock"] * {
        color: var(--ink) !important;
    }

    [data-testid="stFileUploaderDropzone"] {
        background: linear-gradient(180deg, #f9fbfd 0%, #eef3f8 100%) !important;
        border: 1.5px dashed #b5c4d8 !important;
        border-radius: 18px !important;
    }

    [data-testid="stFileUploaderDropzone"] * {
        color: var(--ink) !important;
    }

    [data-testid="stToolbar"] {
        right: 1rem;
    }

    [data-testid="stFileUploader"] [data-testid="stTooltipIcon"] {
        display: none !important;
    }

    @media (max-width: 900px) {
        .hero-title {
            font-size: 2.1rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">Smart Expense Analyzer</div>
      <div class="hero-sub">Upload a bank CSV, auto-categorize uncategorized rows, detect unusual transactions, and export a cleaner categorized file you can actually use.</div>
      <div>
        <span class="chip">Upload CSV</span>
        <span class="chip">Auto-Categorize Rows</span>
        <span class="chip">Review Anomalies</span>
        <span class="chip">Download Clean CSV</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tile1, tile2, tile3 = st.columns(3)
with tile1:
    info_tile("1. Import your statement", "Upload any transaction CSV with date, description, amount, and an optional category column.")
with tile2:
    info_tile("2. Fill missing categories", "The analyzer preserves known categories and predicts labels for uncategorized transactions.")
with tile3:
    info_tile("3. Review the outcome", "Inspect spending patterns, anomaly flags, and download the categorized CSV artifact.")

_db_ref = get_database_ref(PROJECT_ROOT)
try:
    init_db(_db_ref)
    bootstrap_sample_dataset(_db_ref)
except Exception as exc:  # noqa: BLE001
    fallback = PROJECT_ROOT / "data" / "expense_analyzer.db"
    st.warning(f"Primary DB unavailable ({exc}). Using local SQLite fallback.")
    _db_ref = fallback
    init_db(_db_ref)
    bootstrap_sample_dataset(_db_ref)

st.markdown("### Analysis Setup")
c1, c2, c3 = st.columns([1.45, 0.95, 0.9])
with c1:
    upload = st.file_uploader(
        "Upload transaction CSV  |  Required: date, description, amount  |  Optional: category",
        type=["csv"],
    )
with c2:
    seed = st.number_input("Analysis seed", min_value=0, value=42, step=1)
with c3:
    st.write("")
    st.write("")
    reset = st.button("Reset Workspace", use_container_width=True)

if reset:
    st.session_state.clear()
    st.rerun()

if upload is not None:
    file_bytes = upload.getvalue()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    if st.session_state.get("last_uploaded_hash") != file_hash:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(upload.name).stem).strip("_") or "upload"
        dataset_name = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        upload_dir = PROJECT_ROOT / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        csv_path = upload_dir / f"{dataset_name}.csv"
        csv_path.write_bytes(file_bytes)
        count = import_csv_to_dataset(_db_ref, csv_path, dataset_name)
        st.session_state["last_uploaded_hash"] = file_hash
        st.session_state["last_uploaded_dataset"] = dataset_name
        st.success(f"Imported {count} rows into dataset '{dataset_name}'.")

datasets = list_datasets(_db_ref)
default_dataset = st.session_state.get("last_uploaded_dataset")
if datasets and default_dataset in datasets:
    default_index = datasets.index(default_dataset)
else:
    default_index = 0 if datasets else None

st.markdown("### Dataset Filters")
sel1, sel2, sel3 = st.columns([1.35, 1.15, 0.85])
with sel1:
    selected_dataset = st.selectbox("Dataset", options=datasets, index=default_index)
with sel2:
    months = list_months(_db_ref, selected_dataset) if selected_dataset else []
    month_option = st.selectbox("Month", options=["All"] + months, index=0)
with sel3:
    st.write("")
    st.write("")
    run = st.button("Analyze Dataset", use_container_width=True, type="primary")

st.markdown("### Category Management")
cat1, cat2 = st.columns([1.4, 0.8])
with cat1:
    new_category = st.text_input("Add a custom category", placeholder="Examples: Pets, Gifts, Home Office")
with cat2:
    st.write("")
    st.write("")
    add_category_btn = st.button("Save Custom Category", use_container_width=True)

if add_category_btn:
    if new_category.strip():
        add_categories(_db_ref, [(new_category, datetime.utcnow().isoformat(), "manual")])
        st.success(f"Added custom category '{new_category.strip().title()}'.")
    else:
        st.info("Enter a category name first.")

category_options = get_category_options(_db_ref)
if category_options:
    st.caption("Available categories: " + ", ".join(category_options))

if run:
    if not selected_dataset:
        st.error("No dataset available. Upload a CSV first.")
    else:
        with st.spinner("Running classify -> anomaly detect -> report"):
            cfg_path = PROJECT_ROOT / "config.json"
            cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg_data["seed"] = int(seed)
            cfg_path.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")
            cfg = load_config(cfg_path)

            selected_month = None if month_option == "All" else month_option
            txns = load_transactions(_db_ref, selected_dataset, selected_month)
            if not txns:
                st.error("No transactions found for selected dataset/month.")
            else:
                agent = SmartExpenseAgent(cfg)
                result = agent.run_transactions(
                    txns,
                    source_name=f"db:{selected_dataset}:{selected_month or 'all'}",
                    merchant_memory=load_merchant_rules(_db_ref),
                )
                remembered_rows = [
                    (
                        str(row["merchant"]).lower(),
                        str(row["merchant"]),
                        str(row["category"]),
                        float(row["category_confidence"]),
                        str(row["category_source"]),
                        1,
                        datetime.utcnow().isoformat(),
                    )
                    for row in result["categorized_transactions"]
                    if str(row["category"]) != "Other"
                ]
                upsert_merchant_rules(_db_ref, remembered_rows)
                save_run_summary(_db_ref, result, selected_dataset, selected_month)
                st.session_state["result"] = result
                st.session_state["dataset"] = selected_dataset
                st.session_state["month"] = selected_month or "All"

result = st.session_state.get("result")
if not result:
    st.info("Upload CSV (optional), choose dataset/month, then click Run Analysis.")
else:
    st.markdown("### Run Snapshot")
    metrics = result["metrics"]
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_card("State", str(result["state"]), "cyan")
    with k2:
        kpi_card("Transactions", str(metrics["total_transactions"]), "blue")
    with k3:
        kpi_card("Anomalies", str(metrics["anomaly_count"]), "rose")
    with k4:
        kpi_card("Total Spend", f"{metrics['total_spend']:.2f}", "amber")

    st.caption(f"Run ID: {result['run_id']} | Dataset: {st.session_state.get('dataset')} | Month: {st.session_state.get('month')}")

    t1, t2, t3 = st.tabs(["Report", "Anomalies", "Trace"])
    categorized_rows = result.get("categorized_transactions", [])
    recurring_rows = result.get("recurring_expenses", [])

    with t1:
        cats = parse_category_breakdown(result["report"])
        left_tbl, right_chart = st.columns([1.2, 1.8])
        with left_tbl:
            st.markdown("#### Category Breakdown")
            st.dataframe(cats, use_container_width=True)
        with right_chart:
            st.markdown("#### Spend by Category")
            if cats:
                st.bar_chart({row["Category"]: row["Amount"] for row in cats})
        if recurring_rows:
            with st.container(border=True):
                st.markdown("#### Recurring Expenses")
                st.dataframe(recurring_rows, use_container_width=True)
        with st.container(border=True):
            st.markdown("#### Categorized Transactions")
            edited_rows = st.data_editor(
                categorized_rows,
                use_container_width=True,
                num_rows="fixed",
                hide_index=True,
                key="categorized_editor",
                column_config={
                    "category": st.column_config.SelectboxColumn("Category", options=category_options),
                    "category_confidence": st.column_config.NumberColumn("Confidence", format="%.2f", disabled=True),
                    "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
                },
            )
            if st.button("Save Category Corrections", use_container_width=True):
                original_rows = {
                    (str(row["date"]), str(row["description"]), float(row["amount"])): str(row["category"])
                    for row in categorized_rows
                }
                corrections = []
                for row in edited_rows:
                    key = (str(row["date"]), str(row["description"]), float(row["amount"]))
                    if original_rows.get(key) != str(row["category"]):
                        corrections.append(
                            {
                                "date": row["date"],
                                "description": row["description"],
                                "amount": row["amount"],
                                "category": row["category"],
                            }
                        )
                if corrections:
                    applied = apply_category_corrections(_db_ref, str(st.session_state.get("dataset")), corrections)
                    st.success(f"Saved {applied} correction(s). Click Analyze Dataset again to refresh the results.")
                else:
                    st.info("No category changes to save.")
            csv_artifact = Path(str(result["categorized_csv_path"]))
            if csv_artifact.exists():
                st.download_button(
                    "Download Categorized CSV",
                    data=csv_artifact.read_bytes(),
                    file_name=csv_artifact.name,
                    mime="text/csv",
                    use_container_width=True,
                )
        with st.container(border=True):
            st.markdown("#### Full Report")
            st.code(result["report"], language="text")

    with t2:
        anomalies = result.get("anomalies") or parse_anomalies(result["report"])
        feedback_map = load_anomaly_feedback(_db_ref, str(st.session_state.get("dataset")))
        if anomalies:
            st.error(f"Detected {len(anomalies)} anomalies")
            st.dataframe(anomalies, use_container_width=True)
        else:
            st.success("No anomalies detected")
        with st.container(border=True):
            st.markdown("#### Anomaly Review")
            review_rows = build_anomaly_review_candidates(categorized_rows, anomalies)
            if review_rows:
                saved_feedback: list[dict[str, object]] = []
                for idx, row in enumerate(review_rows, start=1):
                    row_key = (row["date"], row["description"], float(row["amount"]))
                    current_feedback = feedback_map.get(row_key, str(row["default_feedback"]))
                    left, right = st.columns([3.2, 1.1])
                    with left:
                        st.markdown(
                            f"**{idx}. {row['description']}**  \n"
                            f"`{row['date']}` | `{row['category']}` | `{float(row['amount']):.2f}`  \n"
                            f"{row['reason']}"
                        )
                    with right:
                        choice = st.selectbox(
                            "Review",
                            options=["Skip", "Anomaly", "Normal"],
                            index=["Skip", "Anomaly", "Normal"].index(current_feedback) if current_feedback in {"Skip", "Anomaly", "Normal"} else 0,
                            key=f"anomaly_review_{idx}_{row['date']}_{row['description']}",
                            label_visibility="collapsed",
                        )
                    if choice != "Skip":
                        saved_feedback.append(
                            {
                                "date": row["date"],
                                "description": row["description"],
                                "amount": row["amount"],
                                "feedback": choice,
                            }
                        )
                if st.button("Save Anomaly Feedback", use_container_width=True):
                    if saved_feedback:
                        saved = save_anomaly_feedback(
                            _db_ref,
                            str(st.session_state.get("dataset")),
                            str(result["run_id"]),
                            saved_feedback,
                        )
                        st.success(f"Saved {saved} anomaly review decision(s).")
                    else:
                        st.info("No anomaly feedback selected.")
            else:
                st.info("No anomalies or borderline candidates available to review in this run.")

    with t3:
        c_left, c_right = st.columns(2)
        with c_left:
            st.markdown("#### State Transitions")
            st.dataframe(result["transitions"], use_container_width=True, hide_index=True)
        with c_right:
            st.markdown("#### Tool Calls")
            log_path = Path(result["log_path"])
            trace_rows = build_tool_trace_rows(log_path)
            if trace_rows:
                st.dataframe(trace_rows, use_container_width=True, hide_index=True)
            else:
                st.info("No tool trace rows available for this run.")

    with st.expander("Run Artifacts"):
        st.write(f"Log: `{result['log_path']}`")
        st.write(f"Report: `{result['report_path']}`")
        st.write(f"Categorized CSV: `{result['categorized_csv_path']}`")
        st.write(f"Merchant Summary CSV: `{result['merchant_summary_csv_path']}`")
        st.write(f"Anomalies CSV: `{result['anomalies_csv_path']}`")
        st.write(f"Summary JSON: `{result['summary_json_path']}`")
        st.write(f"Config: `{result['config_path']}`")
        artifact_cols = st.columns(3)
        artifact_specs = [
            ("Download Merchant Summary", "merchant_summary_csv_path", "text/csv"),
            ("Download Anomalies CSV", "anomalies_csv_path", "text/csv"),
            ("Download Summary JSON", "summary_json_path", "application/json"),
        ]
        for col, (label, key, mime) in zip(artifact_cols, artifact_specs):
            with col:
                artifact_path = Path(str(result[key]))
                if artifact_path.exists():
                    st.download_button(
                        label,
                        data=artifact_path.read_bytes(),
                        file_name=artifact_path.name,
                        mime=mime,
                        use_container_width=True,
                    )
