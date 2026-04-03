"""Statistical anomaly detector using z-score."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev

from .models import AnomalyResult, Transaction
from .reporting import is_expense_transaction, uses_negative_expense_convention


def detect_anomalies(transactions: list[Transaction], z_threshold: float = 2.0) -> list[AnomalyResult]:
    negative_expenses = uses_negative_expense_convention(transactions)
    expense_txns = [t for t in transactions if is_expense_transaction(t, negative_expenses)]
    expenses = [abs(t.amount) for t in expense_txns]
    if len(expenses) < 2:
        return []

    global_avg = mean(expenses)
    global_sigma = pstdev(expenses)
    if global_sigma == 0:
        global_sigma = 1.0

    per_category: dict[str, list[float]] = defaultdict(list)
    for txn in expense_txns:
        per_category[txn.category].append(abs(txn.amount))

    anomalies: list[AnomalyResult] = []
    for txn in expense_txns:
        value = abs(txn.amount)
        category_values = per_category.get(txn.category, [])
        use_category_context = len(category_values) >= 3
        if use_category_context:
            baseline_mean = mean(category_values)
            baseline_sigma = pstdev(category_values) or global_sigma
            context = f"category:{txn.category}"
        else:
            baseline_mean = global_avg
            baseline_sigma = global_sigma
            context = "global"
        z_score = (value - baseline_mean) / baseline_sigma
        if z_score >= z_threshold:
            anomalies.append(
                AnomalyResult(
                    transaction=txn,
                    z_score=z_score,
                    context=context,
                    baseline_mean=baseline_mean,
                )
            )

    return anomalies
