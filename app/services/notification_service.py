from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationService:
    """Create notifications as side-effects of other operations.

    Usage:
        ns = NotificationService(db)
        await ns.create(user_id=..., type="credit_received", title="Top-up Successful", ...)
        # The notification is added to the session but NOT committed.
        # The caller's own `await db.commit()` will persist it.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        type: str,
        title: str,
        body: str | None = None,
        ref_id: str | None = None,
    ) -> Notification:
        n = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            ref_id=ref_id,
        )
        self.db.add(n)
        return n
