from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Scan

logger = logging.getLogger(__name__)

STALE_THRESHOLD_MINUTES = 10


async def cleanup_stale_scans(db: AsyncSession) -> int:
    """Mark scans stuck in 'processing' for >10 minutes as 'failed'.

    Returns the number of scans cleaned up.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)

    result = await db.execute(
        update(Scan)
        .where(Scan.status == "processing", Scan.created_at < cutoff)
        .values(
            status="failed",
            raw_ocr_text=Scan.raw_ocr_text + "\n\nTIMEOUT: processing exceeded 10 minutes",
        )
        .returning(Scan.id)
    )
    stale_ids = result.scalars().all()
    if stale_ids:
        await db.commit()
        logger.warning("Cleaned up %d stale scans: %s", len(stale_ids), stale_ids)
    return len(stale_ids)
