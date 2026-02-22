from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, health, scan, user, webhook, chat


async def lifespan(app: FastAPI):
    # Create tables on startup (dev mode)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ALRI API",
        description="Automated Lab Result Interpreter — backend engine powering web, mobile, and WhatsApp.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

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
    app.include_router(webhook.router)
    app.include_router(chat.router, prefix="/api/v1")

    return app


app = create_app()
