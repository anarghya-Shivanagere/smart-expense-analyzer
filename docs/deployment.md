# Deployment Guide

This app uses a FastAPI backend, a custom static frontend, and a database layer that supports either SQLite or Postgres.

## Quick Local Run

```powershell
python -m pip install -r requirements.txt
python -m uvicorn src.web_app:app --reload --host 127.0.0.1 --port 8503
```

Open:

`http://127.0.0.1:8503`

## Recommended Hosted Deployment

Render is the cleanest option for this project because:

- the app is already configured for FastAPI
- this repo now includes [render.yaml](../render.yaml)
- the database layer supports Render Postgres directly

Important note:

- Streamlit Cloud is no longer the right deployment target for this project
- the app is now a FastAPI web app, not a Streamlit app

## Free Public Link Option

If you want a free shareable link, use a Hugging Face Docker Space.

Why this is the best free fit:

- Docker Spaces support FastAPI apps directly
- you get a public hosted link
- the repo now includes [Dockerfile](../Dockerfile)

Important limitation:

- Hugging Face Spaces free storage is ephemeral
- uploaded CSVs, SQLite data, and generated artifacts can reset when the Space restarts or rebuilds

### Hugging Face Space setup

1. Create an account at [Hugging Face](https://huggingface.co/)
2. Click `New Space`
3. Choose:
   - SDK: `Docker`
   - Visibility: `Public`
4. Create the Space
5. Add the files from this repo to the Space repository
6. Replace the Space `README.md` with [docs/hf-space-readme.md](hf-space-readme.md)
7. Let the Space build

The app will start on port `7860` automatically from [Dockerfile](../Dockerfile).

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

## Render Deployment

This repo includes a ready-to-use [render.yaml](../render.yaml) Blueprint.

### What the Blueprint creates

- one Render web service named `smart-expense-analyzer`
- one Render Postgres database named `smart-expense-analyzer-db`
- an `APP_DB_URL` environment variable wired automatically from the database connection string

### Deploy steps

1. Open [Render Dashboard](https://dashboard.render.com/)
2. Click `New +`
3. Click `Blueprint`
4. Connect your GitHub repository:
   `anarghya-Shivanagere/smart-expense-analyzer`
5. Render will detect [render.yaml](../render.yaml)
6. Review the resources and click `Apply`
7. Wait for the database and web service to finish provisioning
8. Open the generated Render app URL

### Commands used by Render

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn src.web_app:app --host 0.0.0.0 --port $PORT
```

### Why Postgres is used on Render

Render web services use an ephemeral filesystem by default. That means local SQLite files can be lost on redeploy or restart.

Using Render Postgres avoids that problem and keeps:

- uploaded transactions
- learned merchant rules
- anomaly review feedback
- run summaries

persisted across deploys.

## Railway or Other Hosts

If you deploy outside Render, use the same build/start commands and set one of:

- `APP_DB_URL`
- `DATABASE_URL`

to a Postgres connection string if you want persistent hosted data.

## Storage Notes

- SQLite is used by default for local development
- uploaded CSVs are stored under `data/uploads/`
- run artifacts are stored under `runs/`

For a shared team deployment, consider:

- managed Postgres
- authentication before exposing the app publicly
