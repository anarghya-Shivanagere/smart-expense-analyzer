# Smart Expense Analyzer

Smart Expense Analyzer now follows the project requirements with an explicit state machine, tool-driven workflow, observability, reproducibility controls, evaluation harness, UI support, and SQLite persistence.

It now also supports smart categorization for uploaded CSV files:

- Accepts CSVs with `date`, `description`, `amount`, and optional `category`
- Preserves already labeled categories from the CSV
- Learns from labeled rows in the same file to classify uncategorized rows
- Falls back to keyword-based categorization when no learned match is found
- Exports a categorized CSV artifact for download after each run

## Core Flow

Agent behavior is:

1. Load transactions
2. Classify using `categorizer` tool
3. Detect anomalies using statistical `anomaly_detector` tool
4. Generate report with metrics and baseline comparison

UI data flow:

1. Upload CSV (or use sample)
2. Import into SQLite dataset
3. Select dataset + month
4. Run analysis from DB-backed transactions
5. Review and download the categorized CSV

## Requirement Coverage

- Transaction categorizer tool: `src/categorizer.py`
- Statistical anomaly detector tool: `src/anomaly_detector.py`
- Explicit state machine: `src/state_machine.py`
- State transition logging (`previous_state -> event -> next_state`): JSONL logs in `runs/*.jsonl`
- Run ID per execution: generated in `src/agent.py`
- Observability (agent input, tool calls, tool I/O, transitions, timestamps): `src/observability.py` + `src/agent.py`
- Reproducibility seed and run config: `config.json` + `RunConfig`
- Guardrails:
  - tool allowlist
  - max steps per run
  - timeout on tool calls
  - output validation
- Metrics (3+ quantitative): total spend, anomaly count/rate, category coverage
- Baseline comparison (single-agent no-tool baseline): `src/baseline.py`
- Evaluation harness (10 scenarios): `src/evaluation.py`
- UI visibility for state/actions/messages/metrics/run controls: `src/ui_app.py`
- Database layer supports SQLite fallback and Postgres via `APP_DB_URL`/`DATABASE_URL`: `src/database.py`
- `.env.example` included

## Run Demo

```powershell
python -m src.main
```

The run generates artifacts in `runs/`, including:

- JSONL observability log
- text report
- categorized CSV with `category`, `category_source`, and `category_confidence`

## Run Evaluation (10 Scenarios)

```powershell
python -c "from src.evaluation import run_evaluation; print(run_evaluation(seed=42, scenario_count=10))"
```

## Run Tests

```powershell
python -m unittest discover -s tests -v
```

## Launch UI (if Streamlit installed)

```powershell
streamlit run src/ui_app.py
```
