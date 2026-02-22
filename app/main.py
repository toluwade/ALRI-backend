from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, health, scan, user


def create_app() -> FastAPI:
    app = FastAPI(title="ALRI API", version="0.1.0")

    origins = [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"] ,
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(scan.router, prefix="/api/v1")
    app.include_router(user.router, prefix="/api/v1")

    return app


app = create_app()
