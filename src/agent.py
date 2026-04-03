"""Agent orchestration for Smart Expense Analyzer."""

from __future__ import annotations

import csv
import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .anomaly_detector import detect_anomalies
from .baseline import baseline_anomaly_count
from .categorizer import categorize_transactions
from .intelligence import attach_normalized_merchants, detect_recurring_expenses, normalize_merchant
from .models import RunConfig, RunMetrics, Transaction
from .observability import JsonlLogger
from .reporting import compute_metrics, format_report
from .state_machine import AgentState, StateMachine
from .tools import run_with_timeout, validate_anomaly_output, validate_categorized_output


class SmartExpenseAgent:
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.allowed_tools = {"categorizer", "anomaly_detector"}
        self.max_steps = config.max_steps

    def _require_tool_allowed(self, tool_name: str) -> None:
        if tool_name not in self.allowed_tools:
            raise ValueError(f"Tool not allowed: {tool_name}")

    def _load_csv(self, csv_path: Path) -> list[Transaction]:
        transactions: list[Transaction] = []
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                transactions.append(
                    Transaction(
                        date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                        description=row["description"],
                        amount=float(row["amount"]),
                        category=(row.get("category") or "Uncategorized").strip() or "Uncategorized",
                    )
                )
        return transactions

    def _write_categorized_csv(self, run_dir: Path, run_id: str, transactions: list[Transaction]) -> Path:
        output_path = run_dir / f"{run_id}_categorized.csv"
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "description", "merchant", "amount", "category", "category_source", "category_confidence"],
            )
            writer.writeheader()
            for txn in transactions:
                writer.writerow(
                    {
                        "date": txn.date.isoformat(),
                        "description": txn.description,
                        "merchant": txn.merchant or normalize_merchant(txn.description),
                        "amount": txn.amount,
                        "category": txn.category,
                        "category_source": txn.category_source,
                        "category_confidence": f"{txn.category_confidence:.2f}",
                    }
                )
        return output_path

    def _write_merchant_summary_csv(self, run_dir: Path, run_id: str, transactions: list[Transaction]) -> Path:
        summary_path = run_dir / f"{run_id}_merchant_summary.csv"
        grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"count": 0.0, "total_amount": 0.0})
        for txn in transactions:
            merchant = txn.merchant or normalize_merchant(txn.description)
            key = (merchant, txn.category)
            grouped[key]["count"] += 1
            grouped[key]["total_amount"] += abs(txn.amount)
        with summary_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["merchant", "category", "transaction_count", "total_amount"])
            writer.writeheader()
            for (merchant, category), values in sorted(grouped.items(), key=lambda item: (-item[1]["total_amount"], item[0][0])):
                writer.writerow(
                    {
                        "merchant": merchant,
                        "category": category,
                        "transaction_count": int(values["count"]),
                        "total_amount": f"{values['total_amount']:.2f}",
                    }
                )
        return summary_path

    def _write_anomalies_csv(self, run_dir: Path, run_id: str, anomalies: list[dict[str, object]]) -> Path:
        output_path = run_dir / f"{run_id}_anomalies.csv"
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "description", "merchant", "amount", "category", "z_score", "context", "baseline_mean"],
            )
            writer.writeheader()
            for row in anomalies:
                writer.writerow(row)
        return output_path

    def _write_summary_json(self, run_dir: Path, run_id: str, payload: dict[str, object]) -> Path:
        output_path = run_dir / f"{run_id}_summary.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    def _run_pipeline(
        self,
        transactions: list[Transaction],
        input_label: str,
        merchant_memory: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        run_id = str(uuid.uuid4())
        run_dir = Path("runs")
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / f"{run_id}.jsonl"
        logger = JsonlLogger(log_path, run_id)
        machine = StateMachine()
        attach_normalized_merchants(transactions)

        # Per-run reproducibility/config artifact.
        config_path = run_dir / f"{run_id}_config.json"
        config_path.write_text(json.dumps(vars(self.config), indent=2), encoding="utf-8")

        steps = 0

        def step_guard() -> None:
            nonlocal steps
            steps += 1
            if steps > self.max_steps:
                raise RuntimeError("Max steps exceeded")

        logger.log("run_started", {"agent": "SmartExpenseAgent", "config": vars(self.config), "input": input_label})

        try:
            step_guard()
            transition = machine.transition("load_transactions", AgentState.DATA_LOADED)
            logger.log("state_transition", vars(transition))

            step_guard()
            self._require_tool_allowed("categorizer")
            logger.log("tool_call", {"tool": "categorizer", "input_size": len(transactions)})
            categorized = run_with_timeout(
                categorize_transactions,
                self.config.tool_timeout_sec,
                transactions,
                merchant_memory or {},
            )
            validate_categorized_output(categorized)
            logger.log("tool_result", {"tool": "categorizer", "output_size": len(categorized)})
            transition = machine.transition("categorize_transactions", AgentState.CATEGORIZED)
            logger.log("state_transition", vars(transition))

            step_guard()
            self._require_tool_allowed("anomaly_detector")
            logger.log("tool_call", {"tool": "anomaly_detector", "z_threshold": self.config.z_threshold})
            anomalies = run_with_timeout(
                detect_anomalies,
                self.config.tool_timeout_sec,
                categorized,
                self.config.z_threshold,
            )
            validate_anomaly_output(anomalies)
            logger.log("tool_result", {"tool": "anomaly_detector", "output_size": len(anomalies)})
            transition = machine.transition("detect_anomalies", AgentState.ANOMALIES_DETECTED)
            logger.log("state_transition", vars(transition))

            step_guard()
            metrics: RunMetrics = compute_metrics(categorized, anomalies)
            baseline_count = baseline_anomaly_count(categorized)
            recurring_expenses = detect_recurring_expenses(categorized)
            report = format_report(categorized, anomalies, metrics, baseline_count, recurring_expenses)
            transition = machine.transition("generate_report", AgentState.REPORTED)
            logger.log("state_transition", vars(transition))
            logger.log("metrics", vars(metrics))
            logger.log("run_completed", {"final_state": machine.state.value, "baseline_anomaly_count": baseline_count})

            report_path = run_dir / f"{run_id}_report.txt"
            report_path.write_text(report, encoding="utf-8")
            categorized_csv_path = self._write_categorized_csv(run_dir, run_id, categorized)
            anomaly_rows = [
                {
                    "date": item.transaction.date.isoformat(),
                    "description": item.transaction.description,
                    "merchant": item.transaction.merchant,
                    "amount": round(abs(item.transaction.amount), 2),
                    "category": item.transaction.category,
                    "z_score": round(item.z_score, 2),
                    "context": item.context,
                    "baseline_mean": round(item.baseline_mean, 2),
                }
                for item in anomalies
            ]
            merchant_summary_csv_path = self._write_merchant_summary_csv(run_dir, run_id, categorized)
            anomalies_csv_path = self._write_anomalies_csv(run_dir, run_id, anomaly_rows)

            result_payload = {
                "run_id": run_id,
                "state": machine.state.value,
                "transitions": [
                    {
                        "previous_state": t.previous_state.value,
                        "event": t.event,
                        "next_state": t.next_state.value,
                    }
                    for t in machine.history
                ],
                "metrics": vars(metrics),
                "baseline_anomaly_count": baseline_count,
                "report": report,
                "categorized_transactions": [
                    {
                        "date": txn.date.isoformat(),
                        "description": txn.description,
                        "merchant": txn.merchant,
                        "amount": txn.amount,
                        "category": txn.category,
                        "category_source": txn.category_source,
                        "category_confidence": round(txn.category_confidence, 2),
                    }
                    for txn in categorized
                ],
                "recurring_expenses": [
                    {
                        "merchant": item.merchant,
                        "category": item.category,
                        "occurrence_count": item.occurrence_count,
                        "average_amount": round(item.average_amount, 2),
                        "cadence_days": item.cadence_days,
                    }
                    for item in recurring_expenses
                ],
                "anomalies": anomaly_rows,
                "log_path": str(log_path),
                "report_path": str(report_path),
                "categorized_csv_path": str(categorized_csv_path),
                "merchant_summary_csv_path": str(merchant_summary_csv_path),
                "anomalies_csv_path": str(anomalies_csv_path),
                "config_path": str(config_path),
            }
            summary_json_path = self._write_summary_json(run_dir, run_id, result_payload)
            result_payload["summary_json_path"] = str(summary_json_path)
            return result_payload
        except Exception as exc:  # noqa: BLE001
            transition = machine.transition("error", AgentState.FAILED)
            logger.log("state_transition", vars(transition))
            logger.log("run_failed", {"error": str(exc), "final_state": machine.state.value})
            raise

    def run(self, csv_path: Path) -> dict[str, object]:
        transactions = self._load_csv(csv_path)
        return self._run_pipeline(transactions, str(csv_path))

    def run_transactions(
        self,
        transactions: list[Transaction],
        source_name: str = "in_memory",
        merchant_memory: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return self._run_pipeline(transactions, source_name, merchant_memory)


def load_config(path: Path) -> RunConfig:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return RunConfig(
        seed=int(cfg.get("seed", 42)),
        max_steps=int(cfg.get("max_steps", 20)),
        tool_timeout_sec=int(cfg.get("tool_timeout_sec", 2)),
        z_threshold=float(cfg.get("z_threshold", 2.0)),
    )
