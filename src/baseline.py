"""Simple no-tool baseline for comparison."""

from __future__ import annotations

from .models import Transaction
from .reporting import is_expense_transaction, uses_negative_expense_convention


def baseline_anomaly_count(transactions: list[Transaction], threshold: float = 10000.0) -> int:
    negative_expenses = uses_negative_expense_convention(transactions)
    return sum(1 for t in transactions if is_expense_transaction(t, negative_expenses) and abs(t.amount) >= threshold)
