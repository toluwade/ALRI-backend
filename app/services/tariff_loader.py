"""Load platform tariffs from DB (single-row table, created on first access)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tariff import Tariff


async def get_tariffs(db: AsyncSession) -> Tariff:
    """Return the singleton tariff row, creating it with defaults if missing."""
    row = (await db.execute(select(Tariff).where(Tariff.id == 1))).scalar_one_or_none()
    if row is None:
        row = Tariff(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row
