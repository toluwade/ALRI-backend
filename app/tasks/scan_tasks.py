from __future__ import annotations

import asyncio
import uuid

from app.tasks.celery_app import celery_app


def _run(coro):
    """Run an async coroutine from a Celery worker."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running inside an already running loop (rare in celery); create a new one
        return asyncio.run(coro)
    return asyncio.run(coro)


@celery_app.task(name="scan.process_upload")
def process_upload(scan_id: str) -> dict:
    from app.services.scan_pipeline import process_upload_scan

    sid = uuid.UUID(scan_id)
    _run(process_upload_scan(sid))
    return {"status": "ok", "scan_id": scan_id}


@celery_app.task(name="scan.process_manual")
def process_manual(scan_id: str) -> dict:
    from app.services.scan_pipeline import process_manual_scan

    sid = uuid.UUID(scan_id)
    _run(process_manual_scan(sid))
    return {"status": "ok", "scan_id": scan_id}
