"""Medical record router — unified view, PDF export, shareable tokens."""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import MedicalRecordShare, User
from app.routers.auth import get_current_user
from app.services.medical_record import build_medical_record
from app.services.medical_record_pdf import render_medical_record_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medical-record", tags=["medical-record"])

MAX_EXPIRY_DAYS = 90


class ShareCreate(BaseModel):
    expires_in_days: int = Field(7, ge=1, le=MAX_EXPIRY_DAYS)
    note: str | None = Field(None, max_length=500)


class ShareResponse(BaseModel):
    id: str
    url: str
    token: str
    expires_at: str
    note: str | None
    viewed_count: int
    viewed_at: str | None
    revoked_at: str | None
    created_at: str


def _share_to_response(share: MedicalRecordShare) -> ShareResponse:
    return ShareResponse(
        id=str(share.id),
        url=f"{settings.FRONTEND_URL}/shared/record/{share.token}",
        token=share.token,
        expires_at=share.expires_at.isoformat() if share.expires_at else "",
        note=share.note,
        viewed_count=share.viewed_count,
        viewed_at=share.viewed_at.isoformat() if share.viewed_at else None,
        revoked_at=share.revoked_at.isoformat() if share.revoked_at else None,
        created_at=share.created_at.isoformat() if share.created_at else "",
    )


@router.get("")
async def get_record(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_medical_record(db, user.id)


@router.get("/pdf")
async def get_record_pdf(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await build_medical_record(db, user.id)
    pdf_bytes = render_medical_record_pdf(record)
    filename = f"alri-medical-record-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/shares", response_model=list[ShareResponse])
async def list_shares(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(MedicalRecordShare)
            .where(MedicalRecordShare.user_id == user.id)
            .order_by(MedicalRecordShare.created_at.desc())
        )
    ).scalars().all()
    return [_share_to_response(r) for r in rows]


@router.post("/share", response_model=ShareResponse)
async def create_share(
    body: ShareCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = secrets.token_urlsafe(32)[:48]
    expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)
    share = MedicalRecordShare(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
        note=body.note,
        scopes={"all": True},
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return _share_to_response(share)


@router.delete("/share/{share_id}")
async def revoke_share(
    share_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    share = await db.get(MedicalRecordShare, share_id)
    if not share or share.user_id != user.id:
        raise HTTPException(status_code=404, detail="Share not found")
    share.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.get("/shared/{token}")
async def get_shared_record(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public read-only endpoint — no auth required.

    Validates the token, then returns the aggregated record for the
    owning user. Increments viewed_count + sets viewed_at (first view
    is stamped; subsequent views just bump the count).
    """
    result = await db.execute(
        select(MedicalRecordShare).where(MedicalRecordShare.token == token)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Invalid or expired share link")
    if share.revoked_at is not None:
        raise HTTPException(status_code=410, detail="This share link has been revoked")
    now = datetime.now(timezone.utc)
    expires_at = share.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and now > expires_at:
        raise HTTPException(status_code=410, detail="This share link has expired")

    # Record the view (don't block the response on this failing).
    await db.execute(
        update(MedicalRecordShare)
        .where(MedicalRecordShare.id == share.id)
        .values(
            viewed_count=MedicalRecordShare.viewed_count + 1,
            viewed_at=now,
        )
    )
    await db.commit()

    record = await build_medical_record(db, share.user_id)
    return {
        "record": record,
        "share": {
            "note": share.note,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "viewed_count": share.viewed_count + 1,
        },
    }
