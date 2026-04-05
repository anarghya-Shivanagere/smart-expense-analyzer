from __future__ import annotations

import unittest
from datetime import date

from src.categorizer import categorize_transactions
from src.ml_categorizer import predict_category_with_local_ml
from src.models import Transaction


class TestCategorizer(unittest.TestCase):
    def test_categorizes_expected_labels(self) -> None:
        txns = [
            Transaction(date(2026, 2, 1), "Fresh grocery store", -500),
            Transaction(date(2026, 2, 2), "Uber trip", -200),
            Transaction(date(2026, 2, 3), "Electricity bill", -1000),
            Transaction(date(2026, 2, 4), "Unknown merchant", -50),
        ]
        out = categorize_transactions(txns)
        self.assertEqual(out[0].category, "Food")
        self.assertEqual(out[1].category, "Transport")
        self.assertEqual(out[2].category, "Utilities")
        self.assertEqual(out[3].category, "Other")

    def test_learns_from_existing_labeled_rows(self) -> None:
        txns = [
            Transaction(date(2026, 2, 1), "Acme Grocers Koramangala", -500, category="Food"),
            Transaction(date(2026, 2, 2), "Acme Grocers Indiranagar", -650, category="Uncategorized"),
            Transaction(date(2026, 2, 3), "City Cab Airport", -900, category="Transport"),
            Transaction(date(2026, 2, 4), "City Cab Office", -300, category=""),
        ]
        out = categorize_transactions(txns)
        self.assertEqual(out[1].category, "Food")
        self.assertEqual(out[1].category_source, "learned")
        self.assertEqual(out[3].category, "Transport")
        self.assertEqual(out[3].category_source, "learned")

    def test_reduces_fallback_for_common_merchants(self) -> None:
        txns = [
            Transaction(date(2026, 2, 1), "Starbucks coffee", 4.95),
            Transaction(date(2026, 2, 2), "Lyft ride downtown", 17.80),
            Transaction(date(2026, 2, 3), "Hotel stay - Marriott", 410.35),
            Transaction(date(2026, 2, 4), "Online course - Coursera", 39.99),
            Transaction(date(2026, 2, 5), "Bank service fee", 4.00),
        ]
        out = categorize_transactions(txns)
        self.assertEqual([txn.category for txn in out], ["Food", "Transport", "Travel", "Education", "Financial"])

    def test_uses_merchant_memory_across_uploads(self) -> None:
        txns = [Transaction(date(2026, 2, 1), "POS STARBUCKS BANGALORE", 5.25)]
        out = categorize_transactions(
            txns,
            merchant_memory={
                "starbucks bangalore": {
                    "category": "Food",
                    "confidence": 0.91,
                }
            },
        )
        self.assertEqual(out[0].category, "Food")
        self.assertEqual(out[0].category_source, "memory")
        self.assertGreaterEqual(out[0].category_confidence, 0.91)

    def test_keyword_confidence_increases_with_multiple_matches(self) -> None:
        txns = [
            Transaction(date(2026, 2, 1), "Coffee", 120),
            Transaction(date(2026, 2, 2), "Coffee lunch dinner", 240),
        ]
        out = categorize_transactions(txns, use_local_ml=False)
        self.assertEqual(out[0].category_source, "rules")
        self.assertEqual(out[1].category_source, "rules")
        self.assertGreater(out[1].category_confidence, out[0].category_confidence)

    def test_memory_confidence_uses_times_seen_and_source_strength(self) -> None:
        txns = [Transaction(date(2026, 2, 1), "ACME INTERNET PAYMENT", 999)]
        out = categorize_transactions(
            txns,
            merchant_memory={
                "acme internet": {
                    "category": "Utilities",
                    "confidence": 0.82,
                    "source": "manual",
                    "times_seen": 5,
                }
            },
        )
        self.assertEqual(out[0].category_source, "memory")
        self.assertGreater(out[0].category_confidence, 0.82)

    def test_local_ml_classifier_predicts_category(self) -> None:
        training = [
            Transaction(date(2026, 2, 1), "Neighborhood produce market", -320, category="Food"),
            Transaction(date(2026, 2, 2), "City bus commute", -80, category="Transport"),
        ]
        target = Transaction(date(2026, 2, 3), "Produce market purchase", -410)
        category, confidence = predict_category_with_local_ml(target, training, {})
        self.assertEqual(category, "Food")
        self.assertGreater(confidence, 0.4)

if __name__ == "__main__":
    unittest.main()
