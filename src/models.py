"""Data models for Smart Expense Analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Transaction:
    date: date
    description: str
    amount: float
    category: str = "Uncategorized"
    category_source: str = "input"
    category_confidence: float = 0.0
    merchant: str = ""


@dataclass
class AnomalyResult:
    transaction: Transaction
    z_score: float
    context: str = "global"
    baseline_mean: float = 0.0


@dataclass
class RecurringExpense:
    merchant: str
    category: str
    occurrence_count: int
    average_amount: float
    cadence_days: float


@dataclass
class RunConfig:
    seed: int = 42
    max_steps: int = 20
    tool_timeout_sec: int = 2
    z_threshold: float = 2.0
    use_local_ml: bool = True
    ml_min_confidence: float = 0.62


@dataclass
class RunMetrics:
    total_transactions: int
    total_spend: float
    anomaly_count: int
    anomaly_rate: float
    category_coverage: float
