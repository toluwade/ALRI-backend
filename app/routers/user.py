from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import Interpretation, Scan, User
from app.services.credit_manager import CreditManager


router = APIRouter(prefix="/api/v1/user", tags=["user"])


class CreditsResponse(BaseModel):
    credits: int


class ProfileUpdateRequest(BaseModel):
    age: int | None = Field(default=None, ge=0, le=120)
    sex: str | None = Field(default=None, pattern="^(male|female)$")


class ProfileResponse(BaseModel):
    id: uuid.UUID
    email: str | None = None
    phone: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    age: int | None = None
    sex: str | None = None
    credits: int


class ScanListItem(BaseModel):
    id: uuid.UUID
    status: str
    created_at: str | None = None
    summary: str | None = None


class ScanListResponse(BaseModel):
    scans: list[ScanListItem]


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreditsResponse:
    cm = CreditManager(db)
    credits = await cm.get_balance(user.id)
    return CreditsResponse(credits=credits)


@router.post("/profile", response_model=ProfileResponse)
async def update_profile(
    req: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    user.age = req.age
    user.sex = req.sex
    await db.commit()
    await db.refresh(user)
    return ProfileResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        name=user.name,
        avatar_url=user.avatar_url,
        age=user.age,
        sex=user.sex,
        credits=user.credits,
    )


@router.get("/scans", response_model=ScanListResponse)
async def list_scans(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanListResponse:
    # List scans newest first with summary if available
    stmt = (
        select(Scan, Interpretation.summary)
        .outerjoin(Interpretation, Interpretation.scan_id == Scan.id)
        .where(Scan.user_id == user.id)
        .order_by(desc(Scan.created_at))
    )
    res = await db.execute(stmt)
    items: list[ScanListItem] = []
    for scan, summary in res.all():
        items.append(
            ScanListItem(
                id=scan.id,
                status=scan.status,
                created_at=scan.created_at.isoformat() if getattr(scan, "created_at", None) else None,
                summary=summary,
            )
        )

    return ScanListResponse(scans=items)
