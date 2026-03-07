from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationItem(BaseModel):
    id: str
    type: str
    title: str
    body: str | None
    ref_id: str | None
    is_read: bool
    created_at: str


class NotificationsResponse(BaseModel):
    notifications: list[NotificationItem]
    total: int
    unread_count: int
    page: int
    per_page: int


@router.get("", response_model=NotificationsResponse)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationsResponse:
    base_filter = (
        Notification.user_id == current_user.id,
        Notification.type != "login_session",  # legacy spam — no longer created
    )

    total = (
        await db.execute(
            select(func.count()).select_from(Notification).where(*base_filter)
        )
    ).scalar_one()

    unread_count = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(*base_filter, Notification.is_read == False)  # noqa: E712
        )
    ).scalar_one()

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            select(Notification)
            .where(*base_filter)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
    ).scalars().all()

    items = [
        NotificationItem(
            id=str(n.id),
            type=n.type,
            title=n.title,
            body=n.body,
            ref_id=n.ref_id,
            is_read=n.is_read,
            created_at=(
                n.created_at.isoformat()
                if hasattr(n.created_at, "isoformat")
                else str(n.created_at)
            ),
        )
        for n in rows
    ]

    return NotificationsResponse(
        notifications=items,
        total=int(total),
        unread_count=int(unread_count),
        page=page,
        per_page=per_page,
    )


class MarkReadRequest(BaseModel):
    notification_ids: list[str] | None = None  # None = mark all as read


@router.post("/read")
async def mark_read(
    body: MarkReadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = update(Notification).where(
        Notification.user_id == current_user.id,
        Notification.is_read == False,  # noqa: E712
    )

    if body.notification_ids:
        uuids = [uuid.UUID(nid) for nid in body.notification_ids]
        stmt = stmt.where(Notification.id.in_(uuids))

    stmt = stmt.values(is_read=True)
    await db.execute(stmt)
    await db.commit()

    return {"ok": True}
