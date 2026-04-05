"""Smart transaction categorizer with learning from labeled rows."""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .category_definitions import AVAILABLE_CATEGORIES, CATEGORY_KEYWORDS
from .intelligence import attach_normalized_merchants, normalize_merchant
from .ml_categorizer import predict_category_with_local_ml
from .models import Transaction


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


def _score_by_keywords(description: str) -> tuple[str | None, float]:
    text = description.lower()
    best_category: str | None = None
    best_match_count = 0
    best_specificity = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        matched = [keyword for keyword in keywords if keyword in text]
        if not matched:
            continue
        match_count = len(matched)
        specificity = max(len(keyword.replace(" ", "")) for keyword in matched)
        if match_count > best_match_count or (match_count == best_match_count and specificity > best_specificity):
            best_category = category
            best_match_count = match_count
            best_specificity = specificity

    if not best_category:
        return None, 0.0

    confidence = min(
        0.94,
        0.74
        + min(0.12, (best_match_count - 1) * 0.06)
        + min(0.06, max(0, best_specificity - 6) * 0.005),
    )
    return best_category, confidence


def _score_from_memory(remembered: dict[str, object]) -> float:
    stored_confidence = float(remembered.get("confidence", 0.78))
    times_seen = max(1, int(remembered.get("times_seen", 1)))
    source = str(remembered.get("source", "")).lower()
    repetition_bonus = min(0.08, (times_seen - 1) * 0.015)
    source_bonus = 0.04 if source in {"manual", "input"} else 0.0
    return min(0.99, max(0.78, stored_confidence + repetition_bonus + source_bonus))


def categorize_transaction(transaction: Transaction) -> Transaction:
    transaction.category = _normalize_category(transaction.category)
    if not _is_uncategorized(transaction.category):
        transaction.category_source = transaction.category_source or "input"
        transaction.category_confidence = max(transaction.category_confidence, 1.0)
        return transaction

    category, confidence = _score_by_keywords(transaction.description)
    if category:
        transaction.category = category
        transaction.category_source = "rules"
        transaction.category_confidence = confidence
        return transaction
    transaction.category = "Other"
    transaction.category_source = "fallback"
    transaction.category_confidence = 0.35
    return transaction


def categorize_transactions(
    transactions: list[Transaction],
    merchant_memory: dict[str, dict[str, object]] | None = None,
    use_local_ml: bool = True,
    ml_min_confidence: float = 0.62,
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
            txn.category_confidence = _score_from_memory(remembered)
            categorized.append(txn)
            continue

        learned_category, confidence = _score_by_training_data(txn.description, exact_matches, category_tokens)
        if learned_category:
            txn.category = learned_category
            txn.category_source = "learned"
            txn.category_confidence = confidence
        else:
            if use_local_ml:
                ml_category, ml_confidence = predict_category_with_local_ml(txn, transactions, memory)
                if ml_category and ml_confidence >= ml_min_confidence:
                    txn.category = _normalize_category(ml_category)
                    txn.category_source = "ml"
                    txn.category_confidence = ml_confidence
                else:
                    categorize_transaction(txn)
            else:
                categorize_transaction(txn)
        categorized.append(txn)

    return categorized
