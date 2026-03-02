from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import CreditTransaction, Marker, Scan, User
from app.schemas.user import CreditsResponse, PricingInfo, UpdateProfileRequest, UpdateProfileResponse, UserTierInfo
from app.services.credit_manager import CreditManager
from app.services.paystack import initialize_transaction

router = APIRouter(prefix="/user", tags=["user"])


class FundRequest(BaseModel):
    amount_naira: int = Field(..., ge=100, description="Amount to fund in Naira")
    callback_url: str | None = None


class FundResponse(BaseModel):
    authorization_url: str
    access_code: str
    reference: str


@router.get("/credits", response_model=CreditsResponse)
async def credits(current_user: User = Depends(get_current_user)) -> CreditsResponse:
    bal = int(current_user.credits)
    is_paid = CreditManager.is_paid_user(current_user)

    return CreditsResponse(
        balance_kobo=bal,
        balance_naira=bal / 100.0,
        pricing=PricingInfo(
            scan_unlock_naira=settings.PRICE_SCAN_UNLOCK_KOBO / 100,
            chat_message_naira=settings.PRICE_CHAT_MESSAGE_KOBO / 100,
            skin_analysis_naira=settings.PRICE_SKIN_ANALYSIS_KOBO / 100,
            voice_transcription_naira=settings.PRICE_VOICE_TRANSCRIPTION_KOBO / 100,
        ),
        tier=UserTierInfo(
            is_paid_user=is_paid,
            chat_char_limit=settings.CHAT_CHAR_LIMIT_PAID if is_paid else settings.CHAT_CHAR_LIMIT_FREE,
            chat_max_messages=999_999 if is_paid else settings.CHAT_MSG_LIMIT_FREE,
            can_use_skin_analysis=is_paid,
            can_use_voice=is_paid,
        ),
    )


@router.post("/fund", response_model=FundResponse)
async def fund_account(
    body: FundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FundResponse:
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Paystack not configured")

    if not current_user.email:
        raise HTTPException(status_code=400, detail="Email required to fund account")

    amount_kobo = int(body.amount_naira) * 100
    if amount_kobo <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    reference = f"alri_fund_{current_user.id.hex}_{uuid.uuid4().hex[:10]}"

    data = await initialize_transaction(
        email=current_user.email,
        amount_kobo=amount_kobo,
        reference=reference,
        metadata={
            "user_id": str(current_user.id),
            "amount_kobo": amount_kobo,
            "kind": "fund",
        },
        callback_url=body.callback_url or f"{settings.APP_URL.rstrip('/')}/dashboard",
    )

    # record intent (optional) to allow idempotency checks later
    db.add(
        CreditTransaction(
            user_id=current_user.id,
            amount=0,
            reason=f"paystack_init:{reference}"[:50],
            scan_id=None,
        )
    )
    await db.commit()

    return FundResponse(
        authorization_url=data["authorization_url"],
        access_code=data["access_code"],
        reference=data["reference"],
    )


@router.post("/profile", response_model=UpdateProfileResponse)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpdateProfileResponse:
    current_user.age = body.age
    current_user.sex = body.sex
    current_user.weight_kg = body.weight_kg
    current_user.height_cm = body.height_cm
    await db.commit()
    await db.refresh(current_user)
    return UpdateProfileResponse(
        ok=True,
        age=current_user.age,
        sex=current_user.sex,
        weight_kg=current_user.weight_kg,
        height_cm=current_user.height_cm,
    )


class ScanItem(BaseModel):
    id: str
    status: str
    input_type: str | None
    source: str | None
    marker_count: int
    abnormal_count: int
    created_at: str


class ScansResponse(BaseModel):
    scans: list[ScanItem]
    total: int
    page: int
    per_page: int


@router.get("/scans", response_model=ScansResponse)
async def list_scans(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScansResponse:
    # Total count
    total = (
        await db.execute(
            select(func.count()).select_from(Scan).where(Scan.user_id == current_user.id)
        )
    ).scalar_one()

    # Paginated scans
    offset = (page - 1) * per_page
    scans = (
        await db.execute(
            select(Scan)
            .where(Scan.user_id == current_user.id)
            .order_by(Scan.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
    ).scalars().all()

    items: list[ScanItem] = []
    for s in scans:
        markers = (
            await db.execute(select(Marker).where(Marker.scan_id == s.id))
        ).scalars().all()
        abnormal = sum(1 for m in markers if m.status and m.status not in ("normal",))
        items.append(
            ScanItem(
                id=str(s.id),
                status=s.status or "processing",
                input_type=s.input_type,
                source=s.source,
                marker_count=len(markers),
                abnormal_count=abnormal,
                created_at=s.created_at.isoformat() if hasattr(s.created_at, "isoformat") else str(s.created_at),
            )
        )

    return ScansResponse(scans=items, total=int(total), page=page, per_page=per_page)
