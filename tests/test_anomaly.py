from __future__ import annotations

import unittest
from datetime import date

from src.anomaly_detector import detect_anomalies
from src.models import Transaction


class TestAnomalyDetector(unittest.TestCase):
    def test_detects_large_outlier(self) -> None:
        txns = [
            Transaction(date(2026, 1, 1), "grocery", -200),
            Transaction(date(2026, 1, 2), "grocery", -220),
            Transaction(date(2026, 1, 3), "grocery", -250),
            Transaction(date(2026, 1, 4), "rent", -10000),
        ]
        anomalies = detect_anomalies(txns, z_threshold=1.5)
        self.assertEqual(len(anomalies), 1)
        self.assertIn("rent", anomalies[0].transaction.description)

    def test_detects_large_outlier_for_positive_expense_csvs(self) -> None:
        txns = [
            Transaction(date(2026, 1, 1), "grocery", 200),
            Transaction(date(2026, 1, 2), "grocery", 220),
            Transaction(date(2026, 1, 3), "grocery", 250),
            Transaction(date(2026, 1, 4), "rent", 10000),
        ]
        anomalies = detect_anomalies(txns, z_threshold=1.5)
        self.assertEqual(len(anomalies), 1)
        self.assertIn("rent", anomalies[0].transaction.description)


if __name__ == "__main__":
    unittest.main()
