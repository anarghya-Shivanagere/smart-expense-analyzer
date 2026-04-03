"""Evaluation harness with 10 seedable scenarios and baseline comparison."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from .anomaly_detector import detect_anomalies
from .baseline import baseline_anomaly_count
from .categorizer import categorize_transactions
from .models import Transaction


def generate_scenarios(seed: int, scenario_count: int = 10) -> list[dict[str, object]]:
    rng = random.Random(seed)
    scenarios: list[dict[str, object]] = []
    keywords = [
        ("grocery store", "Food"),
        ("uber trip", "Transport"),
        ("electricity bill", "Utilities"),
        ("amazon order", "Shopping"),
        ("movie ticket", "Entertainment"),
    ]

    for s in range(scenario_count):
        txns: list[Transaction] = []
        expected_anomalies: set[int] = set()
        start = date(2026, 1, 1) + timedelta(days=s * 3)

        for i in range(30):
            desc, _cat = rng.choice(keywords)
            amount = -float(rng.randint(200, 3000))
            txns.append(Transaction(date=start + timedelta(days=i % 28), description=desc, amount=amount))

        for i in range(2):
            idx = len(txns)
            expected_anomalies.add(idx)
            txns.append(
                Transaction(
                    date=start + timedelta(days=25 + i),
                    description="emergency hospital payment",
                    amount=-float(rng.randint(12000, 22000)),
                )
            )

        scenarios.append({"transactions": txns, "expected_anomalies": expected_anomalies})

    return scenarios


def _compute_recall(predicted_indices: set[int], expected_indices: set[int]) -> float:
    if not expected_indices:
        return 1.0
    return len(predicted_indices & expected_indices) / len(expected_indices)


def run_evaluation(seed: int = 42, scenario_count: int = 10) -> dict[str, object]:
    scenarios = generate_scenarios(seed=seed, scenario_count=scenario_count)

    per_scenario: list[dict[str, float]] = []
    agent_recalls: list[float] = []
    baseline_recalls: list[float] = []

    for scenario in scenarios:
        txns = categorize_transactions(scenario["transactions"])  # type: ignore[arg-type]
        expected = scenario["expected_anomalies"]  # type: ignore[assignment]

        anomalies = detect_anomalies(txns, z_threshold=2.0)
        predicted = {txns.index(a.transaction) for a in anomalies}
        agent_recall = _compute_recall(predicted, expected)

        baseline_count = baseline_anomaly_count(txns)
        baseline_predicted = set(sorted(range(len(txns)), key=lambda i: abs(txns[i].amount), reverse=True)[:baseline_count])
        baseline_recall = _compute_recall(baseline_predicted, expected)

        agent_recalls.append(agent_recall)
        baseline_recalls.append(baseline_recall)
        per_scenario.append(
            {
                "agent_recall": agent_recall,
                "baseline_recall": baseline_recall,
                "agent_anomaly_count": float(len(anomalies)),
                "baseline_anomaly_count": float(baseline_count),
            }
        )

    result = {
        "seed": seed,
        "scenario_count": scenario_count,
        "agent_avg_recall": sum(agent_recalls) / len(agent_recalls),
        "baseline_avg_recall": sum(baseline_recalls) / len(baseline_recalls),
        "scenarios": per_scenario,
    }

    out_path = Path("runs") / f"evaluation_seed_{seed}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
