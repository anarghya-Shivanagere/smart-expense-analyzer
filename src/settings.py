"""Database configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path


def get_database_ref(project_root: Path) -> str | Path:
    """Return DB reference from env, defaulting to local SQLite path."""
    db_url = os.getenv("APP_DB_URL") or os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    return project_root / "data" / "expense_analyzer.db"

