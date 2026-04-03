from __future__ import annotations

import unittest

from src.evaluation import run_evaluation


class TestEvaluation(unittest.TestCase):
    def test_has_10_scenarios_and_baseline(self) -> None:
        result = run_evaluation(seed=42, scenario_count=10)
        self.assertEqual(result["scenario_count"], 10)
        self.assertIn("agent_avg_recall", result)
        self.assertIn("baseline_avg_recall", result)

    def test_same_seed_same_outputs(self) -> None:
        a = run_evaluation(seed=99, scenario_count=10)
        b = run_evaluation(seed=99, scenario_count=10)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
