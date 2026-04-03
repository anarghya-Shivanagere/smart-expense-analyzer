# Smart Expense Analyzer

Smart Expense Analyzer is a Streamlit app for uploading transaction CSVs, auto-categorizing uncategorized rows, detecting anomalies, spotting recurring expenses, and exporting cleaned analysis artifacts.

## Screenshots

### Home

![Home UI](docs/screenshots/ui-home.png)

### Results

![Results UI](docs/screenshots/ui-results.png)

## Features

- Upload CSV transaction files with `date`, `description`, `amount`, and optional `category`
- Auto-categorize uncategorized rows using:
  - existing input categories
  - merchant memory from previous uploads
  - within-file learning
  - keyword rules
- Detect anomalies with category-aware statistical scoring
- Review recurring expenses
- Collect anomaly feedback from users
- Edit categories in the UI and save corrections
- Add custom categories
- Export:
  - categorized CSV
  - merchant summary CSV
  - anomalies CSV
  - summary JSON
  - report text
  - run logs

## How It Works

### Categorization

Transactions are categorized in layers:

1. Keep the category from the CSV if one already exists
2. Normalize the merchant name from the description
3. Reuse saved merchant memory from previous runs
4. Learn from labeled rows in the same upload
5. Apply rule-based keyword mapping
6. Fall back to `Other`

Main files:

- `src/categorizer.py`
- `src/intelligence.py`
- `src/database.py`

### Anomaly Detection

Anomalies are detected statistically using transaction amounts:

1. Detect whether the dataset uses positive or negative expense values
2. Build a spend baseline
3. Compare each transaction against:
   - its category baseline when enough category data exists
   - otherwise the global dataset baseline
4. Flag rows whose z-score is above the configured threshold

Main file:

- `src/anomaly_detector.py`

## Architecture

See [docs/architecture.md](docs/architecture.md).

State machine:

`INIT -> DATA_LOADED -> CATEGORIZED -> ANOMALIES_DETECTED -> REPORTED`

## Project Structure

```text
src/
  agent.py
  categorizer.py
  anomaly_detector.py
  intelligence.py
  database.py
  reporting.py
  ui_app.py
tests/
data/
docs/
```

## Local Setup

### 1. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

If you do not already have the required packages:

```powershell
python -m pip install streamlit selenium
```

Depending on your environment, you may also need any packages already used by the project such as database or plotting dependencies.

### 3. Run the app

```powershell
python -m streamlit run src/ui_app.py --server.address 127.0.0.1 --server.port 8503
```

Open:

`http://127.0.0.1:8503`

## CLI Usage

Run the sample workflow:

```powershell
python -m src.main
```

Run tests:

```powershell
python -m unittest discover -s tests -v
```

Run evaluation:

```powershell
python -c "from src.evaluation import run_evaluation; print(run_evaluation(seed=42, scenario_count=10))"
```

## Deployment

A deployment guide is available here:

[docs/deployment.md](docs/deployment.md)

## Generated Artifacts

Each run can generate files in `runs/`, including:

- `*_categorized.csv`
- `*_merchant_summary.csv`
- `*_anomalies.csv`
- `*_summary.json`
- `*_report.txt`
- `*.jsonl` observability logs

## Repo

GitHub repository:

[https://github.com/anarghya-Shivanagere/smart-expense-analyzer](https://github.com/anarghya-Shivanagere/smart-expense-analyzer)
