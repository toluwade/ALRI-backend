from __future__ import annotations

import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)

# Try to connect to Redis — if unavailable, fall back to sync execution
_USE_CELERY = False
try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url("redis://localhost:6379/0", socket_connect_timeout=1)
    _r.ping()
    from app.tasks.celery_app import celery_app
    _USE_CELERY = True
    logger.info("Celery/Redis available — using async task queue")
except Exception:
    logger.info("Redis unavailable — running tasks synchronously")


def _run(coro):
    """Run an async coroutine from sync context."""
    import threading

    result = [None]
    error = [None]

    def _thread():
        try:
            result[0] = asyncio.run(coro)
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_thread)
    t.start()
    t.join(timeout=120)

    if error[0]:
        raise error[0]
    return result[0]


class _FallbackTask:
    """Fake Celery task that runs synchronously when Redis/Celery unavailable."""
    def __init__(self, fn):
        self._fn = fn

    def delay(self, *args, **kwargs):
        try:
            self._fn(*args, **kwargs)
        except Exception as e:
            logger.error("Sync task execution failed: %s", e)
        return None

    def __call__(self, *args, **kwargs):
        return self._fn(*args, **kwargs)


def _make_task(fn):
    if _USE_CELERY:
        try:
            return celery_app.task(name=f"scan.{fn.__name__}")(fn)
        except Exception:
            pass
    return _FallbackTask(fn)


def _do_process_upload(scan_id: str, file_path: str, mime_type: str) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings
    from app.services.scan_pipeline import run_upload_pipeline

    async def _inner():
        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with session_factory() as db:
            await run_upload_pipeline(
                db=db,
                scan_id=uuid.UUID(scan_id),
                file_path=file_path,
                mime_type=mime_type,
            )
        await engine.dispose()

    _run(_inner())
    return {"status": "ok", "scan_id": scan_id}


def _do_process_manual(scan_id: str, manual_markers: list[dict]) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings
    from app.services.scan_pipeline import run_manual_pipeline

    async def _inner():
        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with session_factory() as db:
            await run_manual_pipeline(
                db=db,
                scan_id=uuid.UUID(scan_id),
                manual_markers=manual_markers,
            )
        await engine.dispose()

    _run(_inner())
    return {"status": "ok", "scan_id": scan_id}


process_upload = _make_task(_do_process_upload)
process_manual = _make_task(_do_process_manual)
