"""Merchant normalization and recurring-expense helpers."""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

from .models import RecurringExpense, Transaction
from .reporting import is_expense_transaction, uses_negative_expense_convention


_NOISE_WORDS = {
    "pos", "upi", "neft", "imps", "ach", "debit", "credit", "purchase", "payment", "transfer", "txn",
    "transaction", "card", "visa", "mastercard", "ref", "to", "from", "via", "online", "store", "shop",
}


def normalize_merchant(description: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s+]", " ", description.lower())
    tokens = [token for token in text.split() if token and not token.isdigit()]
    cleaned = [token for token in tokens if token not in _NOISE_WORDS]
    if not cleaned:
        cleaned = tokens[:3]
    merchant = " ".join(cleaned[:4]).strip()
    return merchant.title() if merchant else description.strip().title()


def attach_normalized_merchants(transactions: list[Transaction]) -> list[Transaction]:
    for txn in transactions:
        txn.merchant = normalize_merchant(txn.description)
    return transactions


def detect_recurring_expenses(transactions: list[Transaction]) -> list[RecurringExpense]:
    if not transactions:
        return []

    negative_expenses = uses_negative_expense_convention(transactions)
    merchant_groups: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for txn in transactions:
        if not is_expense_transaction(txn, negative_expenses):
            continue
        merchant = txn.merchant or normalize_merchant(txn.description)
        merchant_groups[(merchant, txn.category)].append(txn)

    recurring: list[RecurringExpense] = []
    for (merchant, category), items in merchant_groups.items():
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda item: item.date)
        gaps = [(ordered[idx].date - ordered[idx - 1].date).days for idx in range(1, len(ordered))]
        avg_gap = mean(gaps) if gaps else 0.0
        avg_amount = mean(abs(item.amount) for item in ordered)

        same_day_pattern = len({item.date.day for item in ordered}) <= max(2, len(ordered) // 2)
        steady_gap_pattern = bool(gaps) and 20 <= avg_gap <= 40
        if same_day_pattern or steady_gap_pattern:
            recurring.append(
                RecurringExpense(
                    merchant=merchant,
                    category=category,
                    occurrence_count=len(ordered),
                    average_amount=avg_amount,
                    cadence_days=round(avg_gap, 1) if avg_gap else 0.0,
                )
            )

    return sorted(recurring, key=lambda item: (-item.occurrence_count, item.merchant))
