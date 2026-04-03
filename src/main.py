"""Demo entry point for Smart Expense Analyzer."""

from __future__ import annotations

from pathlib import Path

from .agent import SmartExpenseAgent, load_config


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    cfg = load_config(base_dir / "config.json")
    csv_path = base_dir / "data" / "sample_transactions.csv"

    agent = SmartExpenseAgent(cfg)
    result = agent.run(csv_path)

    print(result["report"])
    print("\nRun ID:", result["run_id"])
    print("Log:", result["log_path"])


if __name__ == "__main__":
    main()
