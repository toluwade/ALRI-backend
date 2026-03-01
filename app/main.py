from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.routers import auth, health, scan, scan_full, skin, user, voice, webhook, chat
from app.services.scan_cleanup import cleanup_stale_scans

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


async def _cleanup_loop():
    """Background loop that cleans up stale scans every 5 minutes."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                count = await cleanup_stale_scans(db)
                if count:
                    logger.info("Cleanup: marked %d stale scans as failed", count)
        except Exception as e:
            logger.error("Scan cleanup error: %s", e)


async def lifespan(app: FastAPI):
    # Create tables on startup (dev mode)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    cleanup_task.cancel()


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
    app.include_router(scan_full.router, prefix="/api/v1")
    app.include_router(user.router, prefix="/api/v1")
    app.include_router(webhook.router)
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(skin.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")

    return app


app = create_app()
