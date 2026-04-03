"""Database persistence layer with SQLite fallback and Postgres-ready support."""

from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .intelligence import normalize_merchant
from .models import Transaction

DBRef = str | Path


def _is_postgres(db_ref: DBRef) -> bool:
    return isinstance(db_ref, str) and db_ref.startswith(("postgresql://", "postgres://"))


def _sqlite_path(db_ref: DBRef) -> Path:
    if isinstance(db_ref, Path):
        return db_ref
    if db_ref.startswith("sqlite:///"):
        return Path(db_ref.replace("sqlite:///", "", 1))
    return Path(db_ref)


def _connect_sqlite(db_ref: DBRef) -> sqlite3.Connection:
    path = _sqlite_path(db_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_postgres(db_url: str) -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Postgres URL configured but psycopg is not installed. Install with: pip install psycopg[binary]"
        ) from exc
    return psycopg.connect(db_url)


def _fetchall(db_ref: DBRef, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _is_postgres(db_ref):
        with closing(_connect_postgres(str(db_ref))) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()
    with closing(_connect_sqlite(db_ref)) as conn:
        return conn.execute(query, params).fetchall()


def _execute(db_ref: DBRef, query: str, params: tuple[Any, ...] = ()) -> None:
    if _is_postgres(db_ref):
        with closing(_connect_postgres(str(db_ref))) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
        return
    with closing(_connect_sqlite(db_ref)) as conn:
        conn.execute(query, params)
        conn.commit()


def _executemany(db_ref: DBRef, query: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    if _is_postgres(db_ref):
        with closing(_connect_postgres(str(db_ref))) as conn:
            with conn.cursor() as cur:
                cur.executemany(query, rows)
            conn.commit()
        return
    with closing(_connect_sqlite(db_ref)) as conn:
        conn.executemany(query, rows)
        conn.commit()


def init_db(db_ref: DBRef) -> None:
    if _is_postgres(db_ref):
        _execute(
            db_ref,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                dataset TEXT NOT NULL,
                date DATE NOT NULL,
                description TEXT NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                category TEXT NOT NULL DEFAULT 'Uncategorized',
                category_source TEXT NOT NULL DEFAULT 'input',
                category_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                imported_at TIMESTAMPTZ NOT NULL
            )
            """,
        )
        _execute(
            db_ref,
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                dataset TEXT NOT NULL,
                month TEXT,
                state TEXT NOT NULL,
                total_transactions INTEGER NOT NULL,
                total_spend DOUBLE PRECISION NOT NULL,
                anomaly_count INTEGER NOT NULL,
                anomaly_rate DOUBLE PRECISION NOT NULL,
                category_coverage DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
        )
        _execute(
            db_ref,
            """
            CREATE TABLE IF NOT EXISTS merchant_rules (
                merchant_key TEXT PRIMARY KEY,
                merchant_display TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                source TEXT NOT NULL,
                times_seen INTEGER NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
        )
        _execute(
            db_ref,
            """
            CREATE TABLE IF NOT EXISTS category_catalog (
                category TEXT PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL,
                source TEXT NOT NULL
            )
            """,
        )
        _execute(
            db_ref,
            """
            CREATE TABLE IF NOT EXISTS anomaly_feedback (
                id SERIAL PRIMARY KEY,
                dataset TEXT NOT NULL,
                run_id TEXT NOT NULL,
                date DATE NOT NULL,
                description TEXT NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                feedback TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
        )
        return

    _execute(
        db_ref,
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL DEFAULT 'Uncategorized',
            category_source TEXT NOT NULL DEFAULT 'input',
            category_confidence REAL NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL
        )
        """,
    )
    if not _is_postgres(db_ref):
        for statement in (
            "ALTER TABLE transactions ADD COLUMN category TEXT NOT NULL DEFAULT 'Uncategorized'",
            "ALTER TABLE transactions ADD COLUMN category_source TEXT NOT NULL DEFAULT 'input'",
            "ALTER TABLE transactions ADD COLUMN category_confidence REAL NOT NULL DEFAULT 0",
        ):
            try:
                _execute(db_ref, statement)
            except sqlite3.OperationalError:
                pass
    _execute(
        db_ref,
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            dataset TEXT NOT NULL,
            month TEXT,
            state TEXT NOT NULL,
            total_transactions INTEGER NOT NULL,
            total_spend REAL NOT NULL,
            anomaly_count INTEGER NOT NULL,
            anomaly_rate REAL NOT NULL,
            category_coverage REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    )
    _execute(
        db_ref,
        """
        CREATE TABLE IF NOT EXISTS merchant_rules (
            merchant_key TEXT PRIMARY KEY,
            merchant_display TEXT NOT NULL,
            category TEXT NOT NULL,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            times_seen INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )
    _execute(
        db_ref,
        """
        CREATE TABLE IF NOT EXISTS category_catalog (
            category TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL
        )
        """,
    )
    _execute(
        db_ref,
        """
        CREATE TABLE IF NOT EXISTS anomaly_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset TEXT NOT NULL,
            run_id TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            feedback TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    )


def import_csv_to_dataset(db_ref: DBRef, csv_path: Path, dataset: str) -> int:
    imported_at = datetime.now(timezone.utc).isoformat()
    rows: list[tuple[str, str, str, float, str, str, float, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = (row.get("category") or "Uncategorized").strip() or "Uncategorized"
            rows.append(
                (
                    dataset,
                    row["date"],
                    row["description"],
                    float(row["amount"]),
                    category,
                    "input",
                    1.0 if category.lower() != "uncategorized" else 0.0,
                    imported_at,
                )
            )

    _execute(db_ref, "DELETE FROM transactions WHERE dataset = %s" if _is_postgres(db_ref) else "DELETE FROM transactions WHERE dataset = ?", (dataset,))
    _executemany(
        db_ref,
        "INSERT INTO transactions(dataset, date, description, amount, category, category_source, category_confidence, imported_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        if _is_postgres(db_ref)
        else "INSERT INTO transactions(dataset, date, description, amount, category, category_source, category_confidence, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    merchant_rows = [
        (normalize_merchant(row[2]), row[2], row[4], 1.0, "input", 1, imported_at)
        for row in rows
        if row[4].lower() != "uncategorized"
    ]
    upsert_merchant_rules(db_ref, merchant_rows)
    add_categories(
        db_ref,
        [
            (row[4], imported_at, "input")
            for row in rows
            if row[4].lower() not in {"uncategorized", "other"}
        ],
    )
    return len(rows)


def add_categories(db_ref: DBRef, categories: list[tuple[str, str, str]]) -> None:
    if not categories:
        return
    unique_rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for category, created_at, source in categories:
        title = str(category).strip().title()
        if not title or title in seen:
            continue
        seen.add(title)
        unique_rows.append((title, created_at, source))
    if not unique_rows:
        return
    if _is_postgres(db_ref):
        _executemany(
            db_ref,
            """
            INSERT INTO category_catalog(category, created_at, source)
            VALUES (%s, %s, %s)
            ON CONFLICT (category) DO NOTHING
            """,
            unique_rows,
        )
        return
    _executemany(
        db_ref,
        """
        INSERT OR IGNORE INTO category_catalog(category, created_at, source)
        VALUES (?, ?, ?)
        """,
        unique_rows,
    )


def list_custom_categories(db_ref: DBRef) -> list[str]:
    rows = _fetchall(db_ref, "SELECT category FROM category_catalog ORDER BY category")
    if _is_postgres(db_ref):
        return [str(r[0]) for r in rows]
    return [str(r["category"]) for r in rows]


def save_anomaly_feedback(
    db_ref: DBRef,
    dataset: str,
    run_id: str,
    feedback_rows: list[dict[str, object]],
) -> int:
    if not feedback_rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            dataset,
            run_id,
            str(item["date"]),
            str(item["description"]),
            float(item["amount"]),
            str(item["feedback"]),
            now,
        )
        for item in feedback_rows
    ]
    _executemany(
        db_ref,
        "INSERT INTO anomaly_feedback(dataset, run_id, date, description, amount, feedback, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if _is_postgres(db_ref)
        else "INSERT INTO anomaly_feedback(dataset, run_id, date, description, amount, feedback, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def load_anomaly_feedback(db_ref: DBRef, dataset: str) -> dict[tuple[str, str, float], str]:
    rows = _fetchall(
        db_ref,
        "SELECT date, description, amount, feedback FROM anomaly_feedback WHERE dataset = %s ORDER BY id DESC"
        if _is_postgres(db_ref)
        else "SELECT date, description, amount, feedback FROM anomaly_feedback WHERE dataset = ? ORDER BY id DESC",
        (dataset,),
    )
    output: dict[tuple[str, str, float], str] = {}
    if _is_postgres(db_ref):
        for row in rows:
            key = (str(row[0]), str(row[1]), float(row[2]))
            output.setdefault(key, str(row[3]))
        return output
    for row in rows:
        key = (str(row["date"]), str(row["description"]), float(row["amount"]))
        output.setdefault(key, str(row["feedback"]))
    return output


def load_merchant_rules(db_ref: DBRef) -> dict[str, dict[str, object]]:
    rows = _fetchall(
        db_ref,
        "SELECT merchant_key, merchant_display, category, confidence, source, times_seen FROM merchant_rules",
    )
    if _is_postgres(db_ref):
        return {
            str(r[0]).lower(): {
                "merchant_display": str(r[1]),
                "category": str(r[2]),
                "confidence": float(r[3]),
                "source": str(r[4]),
                "times_seen": int(r[5]),
            }
            for r in rows
        }
    return {
        str(r["merchant_key"]).lower(): {
            "merchant_display": str(r["merchant_display"]),
            "category": str(r["category"]),
            "confidence": float(r["confidence"]),
            "source": str(r["source"]),
            "times_seen": int(r["times_seen"]),
        }
        for r in rows
    }


def upsert_merchant_rules(db_ref: DBRef, rules: list[tuple[str, str, str, float, str, int, str]]) -> None:
    if not rules:
        return
    if _is_postgres(db_ref):
        _executemany(
            db_ref,
            """
            INSERT INTO merchant_rules(
                merchant_key, merchant_display, category, confidence, source, times_seen, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (merchant_key) DO UPDATE SET
                merchant_display = EXCLUDED.merchant_display,
                category = EXCLUDED.category,
                confidence = EXCLUDED.confidence,
                source = EXCLUDED.source,
                times_seen = merchant_rules.times_seen + EXCLUDED.times_seen,
                updated_at = EXCLUDED.updated_at
            """,
            rules,
        )
        return
    _executemany(
        db_ref,
        """
        INSERT INTO merchant_rules(
            merchant_key, merchant_display, category, confidence, source, times_seen, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(merchant_key) DO UPDATE SET
            merchant_display = excluded.merchant_display,
            category = excluded.category,
            confidence = excluded.confidence,
            source = excluded.source,
            times_seen = merchant_rules.times_seen + excluded.times_seen,
            updated_at = excluded.updated_at
        """,
        rules,
    )


def list_datasets(db_ref: DBRef) -> list[str]:
    rows = _fetchall(db_ref, "SELECT DISTINCT dataset FROM transactions ORDER BY dataset")
    if _is_postgres(db_ref):
        return [str(r[0]) for r in rows]
    return [str(r["dataset"]) for r in rows]


def list_months(db_ref: DBRef, dataset: str) -> list[str]:
    if _is_postgres(db_ref):
        rows = _fetchall(
            db_ref,
            "SELECT DISTINCT to_char(date, 'YYYY-MM') AS month FROM transactions WHERE dataset = %s ORDER BY month",
            (dataset,),
        )
        return [str(r[0]) for r in rows if r[0]]
    rows = _fetchall(
        db_ref,
        "SELECT DISTINCT substr(date, 1, 7) AS month FROM transactions WHERE dataset = ? ORDER BY month",
        (dataset,),
    )
    return [str(r["month"]) for r in rows if r["month"]]


def load_transactions(db_ref: DBRef, dataset: str, month: str | None = None) -> list[Transaction]:
    if _is_postgres(db_ref):
        if month:
            rows = _fetchall(
                db_ref,
                "SELECT date::text, description, amount, category, category_source, category_confidence FROM transactions WHERE dataset = %s AND to_char(date, 'YYYY-MM') = %s ORDER BY date",
                (dataset, month),
            )
        else:
            rows = _fetchall(
                db_ref,
                "SELECT date::text, description, amount, category, category_source, category_confidence FROM transactions WHERE dataset = %s ORDER BY date",
                (dataset,),
            )
        return [
            Transaction(
                date=datetime.strptime(str(r[0]), "%Y-%m-%d").date(),
                description=str(r[1]),
                amount=float(r[2]),
                category=str(r[3]),
                category_source=str(r[4]),
                category_confidence=float(r[5]),
            )
            for r in rows
        ]

    query = "SELECT date, description, amount, category, category_source, category_confidence FROM transactions WHERE dataset = ?"
    params: list[str] = [dataset]
    if month:
        query += " AND substr(date, 1, 7) = ?"
        params.append(month)
    query += " ORDER BY date"
    rows = _fetchall(db_ref, query, tuple(params))
    return [
        Transaction(
            date=datetime.strptime(str(r["date"]), "%Y-%m-%d").date(),
            description=str(r["description"]),
            amount=float(r["amount"]),
            category=str(r["category"]),
            category_source=str(r["category_source"]),
            category_confidence=float(r["category_confidence"]),
        )
        for r in rows
    ]


def save_run_summary(db_ref: DBRef, result: dict[str, object], dataset: str, month: str | None) -> None:
    metrics = result["metrics"]  # type: ignore[index]
    created_at = datetime.now(timezone.utc).isoformat()
    if _is_postgres(db_ref):
        _execute(
            db_ref,
            """
            INSERT INTO runs(
                run_id, dataset, month, state, total_transactions, total_spend,
                anomaly_count, anomaly_rate, category_coverage, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                dataset = EXCLUDED.dataset,
                month = EXCLUDED.month,
                state = EXCLUDED.state,
                total_transactions = EXCLUDED.total_transactions,
                total_spend = EXCLUDED.total_spend,
                anomaly_count = EXCLUDED.anomaly_count,
                anomaly_rate = EXCLUDED.anomaly_rate,
                category_coverage = EXCLUDED.category_coverage,
                created_at = EXCLUDED.created_at
            """,
            (
                str(result["run_id"]),
                dataset,
                month,
                str(result["state"]),
                int(metrics["total_transactions"]),  # type: ignore[index]
                float(metrics["total_spend"]),  # type: ignore[index]
                int(metrics["anomaly_count"]),  # type: ignore[index]
                float(metrics["anomaly_rate"]),  # type: ignore[index]
                float(metrics["category_coverage"]),  # type: ignore[index]
                created_at,
            ),
        )
        return

    _execute(
        db_ref,
        """
        INSERT OR REPLACE INTO runs(
            run_id, dataset, month, state, total_transactions, total_spend,
            anomaly_count, anomaly_rate, category_coverage, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(result["run_id"]),
            dataset,
            month,
            str(result["state"]),
            int(metrics["total_transactions"]),  # type: ignore[index]
            float(metrics["total_spend"]),  # type: ignore[index]
            int(metrics["anomaly_count"]),  # type: ignore[index]
            float(metrics["anomaly_rate"]),  # type: ignore[index]
            float(metrics["category_coverage"]),  # type: ignore[index]
            created_at,
        ),
    )


def apply_category_corrections(
    db_ref: DBRef,
    dataset: str,
    corrections: list[dict[str, object]],
) -> int:
    if not corrections:
        return 0

    applied = 0
    now = datetime.now(timezone.utc).isoformat()
    merchant_rows: list[tuple[str, str, str, float, str, int, str]] = []
    for item in corrections:
        params = (
            str(item["category"]),
            "manual",
            1.0,
            dataset,
            str(item["date"]),
            str(item["description"]),
            float(item["amount"]),
        )
        _execute(
            db_ref,
            "UPDATE transactions SET category = %s, category_source = %s, category_confidence = %s WHERE dataset = %s AND date = %s AND description = %s AND amount = %s"
            if _is_postgres(db_ref)
            else "UPDATE transactions SET category = ?, category_source = ?, category_confidence = ? WHERE dataset = ? AND date = ? AND description = ? AND amount = ?",
            params,
        )
        merchant_rows.append(
            (
                normalize_merchant(str(item["description"])),
                str(item["description"]),
                str(item["category"]),
                1.0,
                "manual",
                1,
                now,
            )
        )
        applied += 1

    upsert_merchant_rules(db_ref, merchant_rows)
    add_categories(
        db_ref,
        [(str(item["category"]), now, "manual") for item in corrections],
    )
    return applied
