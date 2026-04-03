"""Smart transaction categorizer with learning from labeled rows."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable

from .intelligence import attach_normalized_merchants, normalize_merchant
from .models import Transaction


CATEGORY_KEYWORDS: Dict[str, Iterable[str]] = {
    "Food": (
        "restaurant", "cafe", "grocery", "groceries", "food", "swiggy", "zomato", "uber eats",
        "starbucks", "mcdonalds", "bakery", "whole foods", "walmart groceries", "costco bulk groceries",
        "doordash", "pizza", "subway", "kfc", "coffee", "lunch", "dinner", "snacks",
    ),
    "Transport": (
        "uber", "ola", "lyft", "fuel", "petrol", "diesel", "metro", "bus", "train", "parking",
        "gas station", "shell", "ticket fine",
    ),
    "Utilities": ("electricity", "water", "internet", "wifi", "mobile", "bill"),
    "Shopping": (
        "amazon", "flipkart", "mall", "store", "clothing", "electronics", "target", "ikea", "best buy",
        "furniture", "laptop", "shopping", "duty free", "household",
    ),
    "Entertainment": (
        "movie", "netflix", "spotify", "prime", "hotstar", "game", "youtube premium", "disney+",
        "cinema", "concert", "ticket",
    ),
    "Healthcare": ("pharmacy", "hospital", "clinic", "medical", "doctor", "dentist", "prescription"),
    "Rent": ("rent", "landlord", "lease"),
    "Salary": ("salary", "payroll", "income", "credit from employer"),
    "Travel": ("flight", "airlines", "airline", "hotel", "marriott", "hilton", "airbnb", "airport", "lufthansa", "delta"),
    "Education": ("course", "udemy", "coursera", "tuition", "textbook", "textbooks", "school", "bookstore"),
    "Financial": ("interest charge", "service fee", "bank fee", "loan repayment", "atm withdrawal fee", "fee", "insurance premium", "insurance"),
    "Fitness": ("gym", "membership", "workout", "fitness"),
}
AVAILABLE_CATEGORIES: tuple[str, ...] = tuple(CATEGORY_KEYWORDS.keys()) + ("Other",)


UNCATEGORIZED_VALUES = {"", "uncategorized", "un-categorized", "unknown", "na", "n/a", "none", "null"}


def _normalize_category(category: str | None) -> str:
    value = (category or "").strip()
    return value.title() if value else "Uncategorized"


def _is_uncategorized(category: str | None) -> bool:
    return (category or "").strip().lower() in UNCATEGORIZED_VALUES


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1]


def _build_training_signals(transactions: list[Transaction]) -> tuple[dict[str, str], dict[str, Counter[str]]]:
    exact_matches: dict[str, str] = {}
    category_tokens: dict[str, Counter[str]] = defaultdict(Counter)

    for txn in transactions:
        txn.category = _normalize_category(txn.category)
        if _is_uncategorized(txn.category):
            continue
        normalized_desc = " ".join(_tokenize(txn.description))
        if normalized_desc:
            exact_matches[normalized_desc] = txn.category
        exact_matches[normalize_merchant(txn.description).lower()] = txn.category
        category_tokens[txn.category].update(_tokenize(txn.description))

    return exact_matches, category_tokens


def _score_by_training_data(
    description: str,
    exact_matches: dict[str, str],
    category_tokens: dict[str, Counter[str]],
) -> tuple[str | None, float]:
    normalized_desc = " ".join(_tokenize(description))
    if normalized_desc and normalized_desc in exact_matches:
        return exact_matches[normalized_desc], 0.98

    tokens = _tokenize(description)
    if not tokens:
        return None, 0.0

    best_category: str | None = None
    best_score = 0.0
    for category, token_counts in category_tokens.items():
        score = sum(token_counts[token] for token in tokens)
        if score > best_score:
            best_category = category
            best_score = float(score)

    if not best_category or best_score <= 0:
        return None, 0.0

    confidence = min(0.93, 0.45 + (best_score / (best_score + len(tokens))))
    return best_category, confidence


def categorize_transaction(transaction: Transaction) -> Transaction:
    transaction.category = _normalize_category(transaction.category)
    if not _is_uncategorized(transaction.category):
        transaction.category_source = transaction.category_source or "input"
        transaction.category_confidence = max(transaction.category_confidence, 1.0)
        return transaction

    text = transaction.description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            transaction.category = category
            transaction.category_source = "rules"
            transaction.category_confidence = 0.86
            return transaction
    transaction.category = "Other"
    transaction.category_source = "fallback"
    transaction.category_confidence = 0.35
    return transaction


def categorize_transactions(
    transactions: list[Transaction],
    merchant_memory: dict[str, dict[str, object]] | None = None,
) -> list[Transaction]:
    attach_normalized_merchants(transactions)
    exact_matches, category_tokens = _build_training_signals(transactions)
    memory = merchant_memory or {}

    categorized: list[Transaction] = []
    for txn in transactions:
        txn.category = _normalize_category(txn.category)
        if not _is_uncategorized(txn.category):
            txn.category_source = "input"
            txn.category_confidence = 1.0
            categorized.append(txn)
            continue

        merchant_key = (txn.merchant or normalize_merchant(txn.description)).lower()
        remembered = memory.get(merchant_key)
        if remembered and str(remembered.get("category", "")).strip():
            txn.category = _normalize_category(str(remembered["category"]))
            txn.category_source = "memory"
            txn.category_confidence = max(0.78, float(remembered.get("confidence", 0.78)))
            categorized.append(txn)
            continue

        learned_category, confidence = _score_by_training_data(txn.description, exact_matches, category_tokens)
        if learned_category:
            txn.category = learned_category
            txn.category_source = "learned"
            txn.category_confidence = confidence
        else:
            categorize_transaction(txn)
        categorized.append(txn)

    return categorized
