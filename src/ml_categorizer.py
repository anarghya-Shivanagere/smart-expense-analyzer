"""Lightweight local ML categorizer using seeded multinomial naive Bayes."""

from __future__ import annotations

import math
import re
from collections import Counter

from .category_definitions import CATEGORY_KEYWORDS
from .models import Transaction


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1]


def _build_seed_documents() -> dict[str, list[str]]:
    return {category: list(keywords) for category, keywords in CATEGORY_KEYWORDS.items()}


def _build_training_documents(
    transactions: list[Transaction],
    merchant_memory: dict[str, dict[str, object]] | None = None,
) -> dict[str, list[str]]:
    documents = _build_seed_documents()
    for txn in transactions:
        category = (txn.category or "").strip()
        if not category or category.lower() == "uncategorized":
            continue
        documents.setdefault(category, []).append(txn.description)
    for merchant_key, remembered in (merchant_memory or {}).items():
        category = str(remembered.get("category", "")).strip()
        if not category or category == "Other":
            continue
        display = str(remembered.get("merchant_display", merchant_key)).strip()
        documents.setdefault(category, []).append(display)
    return documents


def predict_category_with_local_ml(
    transaction: Transaction,
    transactions: list[Transaction],
    merchant_memory: dict[str, dict[str, object]] | None = None,
) -> tuple[str | None, float]:
    training_docs = _build_training_documents(transactions, merchant_memory)
    category_token_counts: dict[str, Counter[str]] = {}
    category_totals: dict[str, int] = {}
    vocabulary: set[str] = set()

    for category, docs in training_docs.items():
        counts: Counter[str] = Counter()
        for doc in docs:
            counts.update(_tokenize(doc))
        if not counts:
            continue
        category_token_counts[category] = counts
        category_totals[category] = sum(counts.values())
        vocabulary.update(counts.keys())

    tokens = _tokenize(transaction.description)
    if not tokens or not category_token_counts:
        return None, 0.0

    vocab_size = max(1, len(vocabulary))
    total_docs = sum(len(docs) for docs in training_docs.values()) or 1
    log_scores: dict[str, float] = {}

    for category, counts in category_token_counts.items():
        prior = math.log(len(training_docs.get(category, [])) / total_docs)
        total_tokens = category_totals[category]
        score = prior
        for token in tokens:
            token_count = counts.get(token, 0)
            score += math.log((token_count + 1) / (total_tokens + vocab_size))
        log_scores[category] = score

    if not log_scores:
        return None, 0.0

    max_log = max(log_scores.values())
    exp_scores = {category: math.exp(score - max_log) for category, score in log_scores.items()}
    total_score = sum(exp_scores.values()) or 1.0
    probabilities = {category: score / total_score for category, score in exp_scores.items()}
    best_category, best_probability = max(probabilities.items(), key=lambda item: item[1])
    return best_category, float(best_probability)
