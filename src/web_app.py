"""FastAPI app with a modern frontend for Smart Expense Analyzer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import SmartExpenseAgent, load_config
from .categorizer import AVAILABLE_CATEGORIES
from .database import (
    apply_category_corrections,
    import_csv_to_dataset,
    init_db,
    load_anomaly_feedback,
    load_merchant_rules,
    list_custom_categories,
    list_datasets,
    list_months,
    load_transactions,
    save_anomaly_feedback,
    save_run_summary,
    upsert_merchant_rules,
)
from .settings import get_database_ref

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "web"
STATIC_DIR = FRONTEND_DIR / "static"
SAMPLE_DATASET = "sample"


class AnalyzeRequest(BaseModel):
    dataset: str
    month: str | None = None
    seed: int = 42


class CategoryCorrection(BaseModel):
    date: str
    description: str
    amount: float
    category: str


class CorrectionsRequest(BaseModel):
    dataset: str
    corrections: list[CategoryCorrection]


class AnomalyFeedbackItem(BaseModel):
    date: str
    description: str
    amount: float
    feedback: str


class AnomalyFeedbackRequest(BaseModel):
    dataset: str
    run_id: str
    feedback_rows: list[AnomalyFeedbackItem]


app = FastAPI(title="Smart Expense Analyzer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_db_ref() -> str | Path:
    db_ref = get_database_ref(PROJECT_ROOT)
    init_db(db_ref)
    sample_csv = PROJECT_ROOT / "data" / "sample_transactions.csv"
    if SAMPLE_DATASET not in list_datasets(db_ref) and sample_csv.exists():
        import_csv_to_dataset(db_ref, sample_csv, SAMPLE_DATASET)
    return db_ref


def get_category_options(db_ref: str | Path) -> list[str]:
    built_in = list(AVAILABLE_CATEGORIES)
    custom = [category for category in list_custom_categories(db_ref) if category not in built_in]
    return sorted(set(built_in + custom))


def serialize_feedback_map(feedback_map: dict[tuple[str, str, float], str]) -> list[dict[str, object]]:
    return [
        {"date": date, "description": description, "amount": amount, "feedback": feedback}
        for (date, description, amount), feedback in feedback_map.items()
    ]


def get_default_dataset_payload(db_ref: str | Path) -> dict[str, object]:
    datasets = list_datasets(db_ref)
    default_dataset = datasets[0] if datasets else None
    return {
        "datasets": datasets,
        "default_dataset": default_dataset,
        "months": list_months(db_ref, default_dataset) if default_dataset else [],
        "categories": get_category_options(db_ref),
    }


def update_run_seed(seed: int) -> Path:
    cfg_path = PROJECT_ROOT / "config.json"
    cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg_data["seed"] = int(seed)
    cfg_path.write_text(json.dumps(cfg_data, indent=2), encoding="utf-8")
    return cfg_path


def build_remembered_rows(result: dict[str, object]) -> list[tuple[str, str, str, float, str, int, str]]:
    timestamp = datetime.now().isoformat()
    return [
        (
            str(row["merchant"]).lower(),
            str(row["merchant"]),
            str(row["category"]),
            float(row["category_confidence"]),
            str(row["category_source"]),
            1,
            timestamp,
        )
        for row in result["categorized_transactions"]
        if str(row["category"]) != "Other"
    ]


def build_anomaly_review_candidates(
    categorized_rows: list[dict[str, object]],
    anomalies: list[dict[str, object]],
    limit_borderline: int = 5,
) -> list[dict[str, object]]:
    anomaly_keys = {
        (str(row.get("date", "")), str(row.get("description", "")), float(row.get("amount", 0.0)))
        for row in anomalies
    }
    review_rows: list[dict[str, object]] = []
    for row in anomalies:
        review_rows.append(
            {
                "date": str(row["date"]),
                "description": str(row["description"]),
                "amount": float(row["amount"]),
                "category": str(row.get("category", "")),
                "reason": f"Flagged anomaly ({row.get('context', 'global')})",
                "default_feedback": "Anomaly",
            }
        )
    borderline = sorted(
        [
            row
            for row in categorized_rows
            if (str(row["date"]), str(row["description"]), abs(float(row["amount"]))) not in anomaly_keys
        ],
        key=lambda row: abs(float(row["amount"])),
        reverse=True,
    )[:limit_borderline]
    for row in borderline:
        review_rows.append(
            {
                "date": str(row["date"]),
                "description": str(row["description"]),
                "amount": abs(float(row["amount"])),
                "category": str(row.get("category", "")),
                "reason": "High-value transaction worth reviewing",
                "default_feedback": "Normal",
            }
        )
    return review_rows


def attach_supporting_payload(result: dict[str, object], dataset: str, db_ref: str | Path) -> dict[str, object]:
    result = dict(result)
    result["category_options"] = get_category_options(db_ref)
    feedback_map = load_anomaly_feedback(db_ref, dataset)
    result["anomaly_feedback"] = serialize_feedback_map(feedback_map)
    result["anomaly_review_candidates"] = build_anomaly_review_candidates(
        list(result.get("categorized_transactions", [])),
        list(result.get("anomalies", [])),
    )
    return result


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((FRONTEND_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, object]:
    db_ref = get_db_ref()
    return get_default_dataset_payload(db_ref)


@app.post("/api/upload")
async def upload_csv(request: Request, filename: str = Query("upload.csv")) -> dict[str, object]:
    db_ref = get_db_ref()
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in Path(filename).stem).strip("_") or "upload"
    dataset_name = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    upload_dir = PROJECT_ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    csv_path = upload_dir / f"{dataset_name}.csv"
    csv_path.write_bytes(await request.body())
    count = import_csv_to_dataset(db_ref, csv_path, dataset_name)
    return {
        "dataset": dataset_name,
        "row_count": count,
        "months": list_months(db_ref, dataset_name),
    }


@app.get("/api/datasets/{dataset}/months")
def dataset_months(dataset: str) -> dict[str, object]:
    db_ref = get_db_ref()
    return {"months": list_months(db_ref, dataset)}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, object]:
    db_ref = get_db_ref()
    cfg_path = update_run_seed(request.seed)
    cfg = load_config(cfg_path)

    month = None if request.month in {None, "", "All"} else request.month
    txns = load_transactions(db_ref, request.dataset, month)
    if not txns:
        raise HTTPException(status_code=404, detail="No transactions found for selected dataset/month.")

    agent = SmartExpenseAgent(cfg)
    result = agent.run_transactions(
        txns,
        source_name=f"db:{request.dataset}:{month or 'all'}",
        merchant_memory=load_merchant_rules(db_ref),
    )
    remembered_rows = build_remembered_rows(result)
    upsert_merchant_rules(db_ref, remembered_rows)
    save_run_summary(db_ref, result, request.dataset, month)
    return attach_supporting_payload(result, request.dataset, db_ref)


@app.post("/api/corrections")
def save_corrections(request: CorrectionsRequest) -> dict[str, object]:
    db_ref = get_db_ref()
    applied = apply_category_corrections(db_ref, request.dataset, [item.model_dump() for item in request.corrections])
    return {"applied": applied, "categories": get_category_options(db_ref)}


@app.post("/api/anomaly-feedback")
def save_feedback(request: AnomalyFeedbackRequest) -> dict[str, object]:
    db_ref = get_db_ref()
    saved = save_anomaly_feedback(db_ref, request.dataset, request.run_id, [item.model_dump() for item in request.feedback_rows])
    return {"saved": saved}


@app.get("/api/download")
def download_artifact(path: str = Query(...)) -> FileResponse:
    requested = Path(path)
    if not requested.is_absolute():
        requested = (PROJECT_ROOT / requested).resolve()
    else:
        requested = requested.resolve()
    allowed_roots = [(PROJECT_ROOT / "runs").resolve(), (PROJECT_ROOT / "data").resolve()]
    if not any(root in requested.parents or requested == root for root in allowed_roots):
        raise HTTPException(status_code=400, detail="Artifact path is not allowed.")
    if not requested.exists():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(requested)


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - convenience launcher
        raise SystemExit(
            "uvicorn is required to run the new frontend. Install dependencies from requirements.txt and run "
            "`python -m uvicorn src.web_app:app --reload`."
        ) from exc

    uvicorn.run("src.web_app:app", host="127.0.0.1", port=8503, reload=True)
