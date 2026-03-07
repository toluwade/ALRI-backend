from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.routers import auth, health, notification, scan, scan_full, skin, user, voice, webhook, chat
from app.services.scan_cleanup import cleanup_stale_scans
from app.models.notification import Notification

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
NOTIFICATION_CLEANUP_INTERVAL = 3600  # check every hour
NOTIFICATION_MAX_AGE_HOURS = 24


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


async def _notification_cleanup_loop():
    """Background loop that purges notifications older than 24 hours."""
    while True:
        await asyncio.sleep(NOTIFICATION_CLEANUP_INTERVAL)
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=NOTIFICATION_MAX_AGE_HOURS)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    delete(Notification).where(Notification.created_at < cutoff)
                )
                count = result.rowcount
                await db.commit()
                if count:
                    logger.info("Notification cleanup: deleted %d entries older than %dh", count, NOTIFICATION_MAX_AGE_HOURS)
        except Exception as e:
            logger.error("Notification cleanup error: %s", e)


async def lifespan(app: FastAPI):
    # Create tables on startup (dev mode)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # One-time: purge all legacy login_session spam notifications
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(Notification).where(Notification.type == "login_session")
            )
            if result.rowcount:
                logger.info("Startup: purged %d login_session notifications", result.rowcount)
            await db.commit()
    except Exception as e:
        logger.warning("Startup notification purge failed: %s", e)

    cleanup_task = asyncio.create_task(_cleanup_loop())
    notif_task = asyncio.create_task(_notification_cleanup_loop())
    yield
    cleanup_task.cancel()
    notif_task.cancel()


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
    app.include_router(notification.router, prefix="/api/v1")

    return app


app = create_app()
