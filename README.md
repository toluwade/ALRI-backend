# ALRI Backend API (alri-api)

FastAPI backend for ALRI (Automated Lab Result Interpreter).

## Local development

1. Copy env file:

```bash
cp .env.example .env
```

2. Start services:

```bash
docker compose up --build
```

API will be available at `http://localhost:8000`.

## Services

- API: FastAPI + Uvicorn
- Worker: Celery worker for async scan processing
- DB: Postgres
- Cache/queue: Redis

## Key endpoints

- `GET /api/v1/health`
- `POST /api/v1/scan/upload`
- `GET /api/v1/scan/{id}/preview` (no auth)
- `GET /api/v1/scan/{id}/full` (auth + 1 credit)
- `GET /api/v1/user/credits`
- `POST /api/v1/user/profile`
- `GET /api/v1/user/scans`
- `GET/POST /api/v1/webhook/whatsapp`

## Notes

- Full scan access deducts 1 credit on first access per scan; subsequent views are free.
- AI results are informational only and not medical advice.
