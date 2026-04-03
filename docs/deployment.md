# Deployment Guide

This project is a Streamlit application, so the simplest deployment targets are:

- Streamlit Community Cloud
- a VM or cloud server running Python
- Docker on any hosting platform

## Option 1: Streamlit Community Cloud

Best for a quick demo deployment.

### Steps

1. Push the repo to GitHub
2. Go to [https://share.streamlit.io](https://share.streamlit.io)
3. Click `New app`
4. Select this repository:
   - `anarghya-Shivanagere/smart-expense-analyzer`
5. Set the main file path to:

```text
src/ui_app.py
```

6. Deploy

### Notes

- Make sure all required Python dependencies are installed in the deployment environment
- If you want smoother deployment later, add a `requirements.txt`

## Option 2: Run on a Server

### Steps

1. Clone the repo

```bash
git clone https://github.com/anarghya-Shivanagere/smart-expense-analyzer.git
cd smart-expense-analyzer
```

2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\Activate.ps1
```

3. Install dependencies

```bash
python -m pip install streamlit selenium
```

4. Run Streamlit

```bash
python -m streamlit run src/ui_app.py --server.address 0.0.0.0 --server.port 8503
```

5. Expose port `8503` through your firewall or reverse proxy

## Option 3: Docker

You can containerize the app for deployment on:

- Render
- Railway
- Azure
- AWS
- GCP
- DigitalOcean

Suggested future additions:

- `requirements.txt`
- `Dockerfile`
- optional `Procfile`

## Environment Notes

- The app uses local SQLite by default
- Uploaded CSVs and run artifacts are stored locally unless you change storage behavior
- For shared/team deployment, consider:
  - persistent volume storage
  - database-backed storage
  - authentication if exposing publicly

## Recommended Next Deployment Improvements

1. Add `requirements.txt`
2. Add `Dockerfile`
3. Add environment variable documentation
4. Move run artifacts to durable storage for hosted environments
