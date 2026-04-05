# Deployment Guide

This app uses a FastAPI backend, a custom static frontend, local file-based artifacts, and SQLite by default.

## Quick Local Run

```powershell
python -m pip install -r requirements.txt
python -m uvicorn src.web_app:app --reload --host 127.0.0.1 --port 8503
```

Open:

`http://127.0.0.1:8503`

## Good Deployment Targets

- Render
- Railway
- a VPS or VM
- Docker-based hosting

## Server Deployment

### 1. Clone the repository

```bash
git clone https://github.com/anarghya-Shivanagere/smart-expense-analyzer.git
cd smart-expense-analyzer
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Start the app

```bash
python -m uvicorn src.web_app:app --host 0.0.0.0 --port 8503
```

### 5. Put a reverse proxy in front

Use Nginx or Caddy if the app is exposed publicly.

## Render or Railway

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn src.web_app:app --host 0.0.0.0 --port $PORT
```

## Storage Notes

- SQLite is used by default
- uploaded CSVs are stored under `data/uploads/`
- run artifacts are stored under `runs/`

For a shared team deployment, consider:

- persistent disk/volume storage
- a managed Postgres database
- authentication before exposing the app publicly
