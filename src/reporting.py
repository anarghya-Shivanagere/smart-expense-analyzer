"""Reporting and metric helpers."""

from __future__ import annotations

from collections import defaultdict

from .models import AnomalyResult, RecurringExpense, RunMetrics, Transaction


def uses_negative_expense_convention(transactions: list[Transaction]) -> bool:
    return any(txn.amount < 0 for txn in transactions)


def is_expense_transaction(transaction: Transaction, negative_expenses: bool) -> bool:
    return transaction.amount < 0 if negative_expenses else transaction.amount > 0


def generate_monthly_summary(transactions: list[Transaction]) -> dict[str, float]:
    negative_expenses = uses_negative_expense_convention(transactions)
    totals: dict[str, float] = defaultdict(float)
    for txn in transactions:
        if is_expense_transaction(txn, negative_expenses):
            totals[txn.category] += abs(txn.amount)
    return dict(sorted(totals.items(), key=lambda kv: kv[0]))


def compute_metrics(transactions: list[Transaction], anomalies: list[AnomalyResult]) -> RunMetrics:
    negative_expenses = uses_negative_expense_convention(transactions)
    expense_txns = [t for t in transactions if is_expense_transaction(t, negative_expenses)]
    categorized = [t for t in expense_txns if t.category and t.category != "Uncategorized"]
    total_spend = sum(abs(t.amount) for t in expense_txns)
    anomaly_count = len(anomalies)
    anomaly_rate = anomaly_count / len(expense_txns) if expense_txns else 0.0
    category_coverage = len(categorized) / len(expense_txns) if expense_txns else 0.0
    return RunMetrics(
        total_transactions=len(transactions),
        total_spend=total_spend,
        anomaly_count=anomaly_count,
        anomaly_rate=anomaly_rate,
        category_coverage=category_coverage,
    )


def format_report(
    transactions: list[Transaction],
    anomalies: list[AnomalyResult],
    metrics: RunMetrics,
    baseline_anomaly_count: int,
    recurring_expenses: list[RecurringExpense] | None = None,
) -> str:
    if not transactions:
        return "No transactions available."

    month_label = transactions[0].date.strftime("%B %Y")
    summary = generate_monthly_summary(transactions)

    lines: list[str] = []
    lines.append(f"Smart Expense Analyzer Report - {month_label}")
    lines.append("=" * 60)
    lines.append(f"Total Transactions: {metrics.total_transactions}")
    lines.append(f"Total Spend: {metrics.total_spend:.2f}")
    lines.append(f"Anomaly Detection Count: {metrics.anomaly_count}")
    lines.append(f"Anomaly Rate: {metrics.anomaly_rate:.2%}")
    lines.append(f"Category Coverage: {metrics.category_coverage:.2%}")
    auto_categorized = sum(1 for txn in transactions if txn.category_source in {"learned", "rules", "fallback"})
    lines.append(f"Auto-Categorized Rows: {auto_categorized}")
    lines.append("")
    lines.append("Category Breakdown:")

    for category, value in summary.items():
        lines.append(f"- {category:<14} {value:>10.2f}")

    lines.append("")
    lines.append("Anomaly Count Comparison:")
    lines.append(f"- Simple threshold reference: {baseline_anomaly_count}")
    lines.append(f"- Smart analyzer result:      {metrics.anomaly_count}")

    if recurring_expenses:
        lines.append("")
        lines.append("Recurring Expenses:")
        for item in recurring_expenses:
            cadence = f"{item.cadence_days:.1f}d" if item.cadence_days else "calendar-like"
            lines.append(
                f"- {item.merchant} | {item.category} | avg={item.average_amount:.2f} | repeats={item.occurrence_count} | cadence={cadence}"
            )

    if anomalies:
        lines.append("")
        lines.append("Anomalies:")
        for item in anomalies:
            txn = item.transaction
            lines.append(
                f"- {txn.date.isoformat()} | {txn.description} | {abs(txn.amount):.2f} | z={item.z_score:.2f} | {item.context}"
            )

    return "\n".join(lines)
