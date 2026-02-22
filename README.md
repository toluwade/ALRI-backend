# ALRI API (alri-api)

FastAPI backend for **ALRI (Automated Lab Result Interpreter)**.

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose up --build
```

API:
- `GET http://localhost:8000/api/v1/health`

## Local dev

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Migrations

```bash
alembic upgrade head
```
