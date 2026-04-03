from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from src.agent import SmartExpenseAgent, load_config
from src.models import Transaction


class TestAgentFlow(unittest.TestCase):
    def test_end_to_end_report_and_logs(self) -> None:
        cfg = load_config(Path("config.json"))
        agent = SmartExpenseAgent(cfg)
        result = agent.run(Path("data/sample_transactions.csv"))

        self.assertEqual(result["state"], "REPORTED")
        self.assertIn("Anomaly Detection Count", result["report"])
        self.assertGreaterEqual(result["metrics"]["anomaly_count"], 1)
        self.assertIn("categorized_transactions", result)
        self.assertTrue(Path(result["categorized_csv_path"]).exists())
        self.assertIn("recurring_expenses", result)
        self.assertIn("anomalies", result)
        self.assertTrue(Path(result["merchant_summary_csv_path"]).exists())
        self.assertTrue(Path(result["anomalies_csv_path"]).exists())
        self.assertTrue(Path(result["summary_json_path"]).exists())

        config_path = Path(result["config_path"])
        self.assertTrue(config_path.exists())

        log_path = Path(result["log_path"])
        self.assertTrue(log_path.exists())
        rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        event_types = {r["event_type"] for r in rows}
        self.assertIn("state_transition", event_types)
        self.assertIn("tool_call", event_types)
        self.assertIn("tool_result", event_types)

    def test_positive_expense_transactions_produce_spend_summary(self) -> None:
        cfg = load_config(Path("config.json"))
        agent = SmartExpenseAgent(cfg)
        txns = [
            Transaction(date(2026, 1, 1), "Walmart groceries", 54.23),
            Transaction(date(2026, 1, 2), "Uber ride", 23.50),
            Transaction(date(2026, 1, 3), "Electricity bill", 92.30),
        ]
        result = agent.run_transactions(txns, source_name="positive-expense-demo")
        self.assertGreater(result["metrics"]["total_spend"], 0)
        self.assertIn("Transport", result["report"])
        self.assertIn("Utilities", result["report"])

    def test_detects_recurring_expenses(self) -> None:
        cfg = load_config(Path("config.json"))
        agent = SmartExpenseAgent(cfg)
        txns = [
            Transaction(date(2026, 1, 5), "Netflix subscription", 15.49),
            Transaction(date(2026, 2, 5), "Netflix subscription", 15.49),
            Transaction(date(2026, 3, 5), "Netflix subscription", 15.49),
        ]
        result = agent.run_transactions(txns, source_name="recurring-demo")
        self.assertTrue(result["recurring_expenses"])
        self.assertEqual(result["recurring_expenses"][0]["merchant"], "Netflix Subscription")


if __name__ == "__main__":
    unittest.main()
