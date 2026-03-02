# Dummy Calculator API

Minimal HTTP API for exercising a PR workflow.

## Setup

Create and activate a virtual environment, then install deps.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux/macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Open docs at `http://127.0.0.1:8000/docs`.

## Quick test

### Health

```bash
curl http://127.0.0.1:8000/health
```

### Calculate (POST)

```bash
curl -X POST http://127.0.0.1:8000/calc \
  -H "Content-Type: application/json" \
  -d '{"op":"add","a":2,"b":3}'
```

### Calculate (GET)

```bash
curl "http://127.0.0.1:8000/calc/div?a=10&b=2"
```
