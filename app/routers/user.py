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
        callback_url=body.callback_url or f"{settings.FRONTEND_URL.rstrip('/')}/dashboard",
    )

    # record intent (optional) to allow idempotency checks later
    db.add(
        CreditTransaction(
            user_id=current_user.id,
            amount=0,
            reason=f"paystack_init:{reference}",
            scan_id=None,
        )
    )
    await db.commit()

    return FundResponse(
        authorization_url=data["authorization_url"],
        access_code=data["access_code"],
        reference=data["reference"],
    )


class VerifyPaymentRequest(BaseModel):
    reference: str


class VerifyPaymentResponse(BaseModel):
    status: str
    amount_kobo: int = 0
    balance_after_kobo: int = 0
    is_paid_user: bool = False


@router.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_payment(
    body: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerifyPaymentResponse:
    """Verify a Paystack payment by reference and credit the user.

    This complements the webhook — called by the frontend after the user
    returns from Paystack. Uses the same idempotency logic as the webhook
    to avoid double-crediting.
    """
    from app.services.paystack import verify_transaction
    from app.services.notification_service import NotificationService

    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Paystack not configured")

    reference = body.reference.strip()
    if not reference:
        raise HTTPException(status_code=400, detail="Missing reference")

    # Idempotency: already credited?
    reason = f"paystack_success:{reference}"
    existing = (
        await db.execute(
            select(CreditTransaction.id).where(CreditTransaction.reason == reason)
        )
    ).scalar_one_or_none()
    if existing:
        return VerifyPaymentResponse(
            status="already_credited",
            balance_after_kobo=int(current_user.credits),
            is_paid_user=CreditManager.is_paid_user(current_user),
        )

    # Verify with Paystack
    try:
        verified = await verify_transaction(reference)
    except Exception:
        raise HTTPException(status_code=502, detail="Could not verify with Paystack")

    if verified.get("status") != "success":
        return VerifyPaymentResponse(status="not_successful", is_paid_user=CreditManager.is_paid_user(current_user))

    amount_kobo = int(verified.get("amount") or 0)
    if amount_kobo <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    # Ensure this payment belongs to the current user
    metadata = verified.get("metadata") or {}
    payment_user_id = metadata.get("user_id")
    if payment_user_id and str(payment_user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Payment does not belong to this user")

    # Credit the user
    current_user.credits += amount_kobo
    current_user.has_topped_up = True
    db.add(
        CreditTransaction(
            user_id=current_user.id,
            amount=amount_kobo,
            reason=reason,
            scan_id=None,
        )
    )
    await NotificationService(db).create(
        user_id=current_user.id,
        type="credit_received",
        title="Top-up Successful",
        body=f"₦{amount_kobo // 100:,} has been added to your balance.",
    )
    await db.commit()
    await db.refresh(current_user)

    return VerifyPaymentResponse(
        status="credited",
        amount_kobo=amount_kobo,
        balance_after_kobo=int(current_user.credits),
        is_paid_user=CreditManager.is_paid_user(current_user),
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


# ------------------------------------------------------------------
# Transaction history
# ------------------------------------------------------------------

_REASON_MAP: dict[str, tuple[str, str]] = {
    "scan_used": ("deduction", "Scan Unlock"),
    "chat_used": ("deduction", "Chat Message"),
    "skin_analysis": ("deduction", "Skin Analysis"),
    "voice_used": ("deduction", "Voice Transcription"),
    "file_upload": ("deduction", "File Upload"),
    "grant": ("reward", "Credit Bonus"),
}


def _classify_reason(reason: str, amount: int) -> tuple[str, str]:
    """Derive a category and human-readable label from the raw reason."""
    if reason in _REASON_MAP:
        return _REASON_MAP[reason]
    if reason.startswith("paystack_success:"):
        return ("topup", "Paystack Top-up")
    if reason.startswith("paystack_init:"):
        return ("init", "Payment Initiated")
    if "referral" in reason.lower():
        return ("reward", "Referral Reward")
    if "tester" in reason.lower():
        return ("reward", "Tester Reward")
    return ("reward" if amount > 0 else "deduction", reason.replace("_", " ").title())


class TransactionItem(BaseModel):
    id: str
    amount: int
    amount_naira: float
    reason: str
    category: str
    label: str
    scan_id: str | None
    created_at: str


class TransactionsResponse(BaseModel):
    transactions: list[TransactionItem]
    total: int
    page: int
    per_page: int
    new_count: int


@router.get("/transactions", response_model=TransactionsResponse)
async def list_transactions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    since: str | None = Query(default=None, description="ISO timestamp — count new transactions after this"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionsResponse:
    from datetime import datetime, timezone

    base_filter = [
        CreditTransaction.user_id == current_user.id,
        ~CreditTransaction.reason.startswith("paystack_init:"),
    ]

    total = (
        await db.execute(
            select(func.count()).select_from(CreditTransaction).where(*base_filter)
        )
    ).scalar_one()

    # Count new transactions since the given timestamp
    new_count = 0
    if since:
        try:
            since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
            new_count = (
                await db.execute(
                    select(func.count())
                    .select_from(CreditTransaction)
                    .where(*base_filter, CreditTransaction.created_at > since_dt)
                )
            ).scalar_one()
            new_count = int(new_count)
        except (ValueError, TypeError):
            new_count = 0

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            select(CreditTransaction)
            .where(*base_filter)
            .order_by(CreditTransaction.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
    ).scalars().all()

    items: list[TransactionItem] = []
    for tx in rows:
        cat, label = _classify_reason(tx.reason, tx.amount)
        items.append(
            TransactionItem(
                id=str(tx.id),
                amount=tx.amount,
                amount_naira=tx.amount / 100.0,
                reason=tx.reason,
                category=cat,
                label=label,
                scan_id=str(tx.scan_id) if tx.scan_id else None,
                created_at=(
                    tx.created_at.isoformat()
                    if hasattr(tx.created_at, "isoformat")
                    else str(tx.created_at)
                ),
            )
        )

    return TransactionsResponse(
        transactions=items,
        total=int(total),
        page=page,
        per_page=per_page,
        new_count=new_count,
    )


# ------------------------------------------------------------------
# Promo code redemption
# ------------------------------------------------------------------

class RedeemPromoRequest(BaseModel):
    code: str


class RedeemPromoResponse(BaseModel):
    ok: bool
    credited_kobo: int = 0
    balance_after_kobo: int = 0
    message: str = ""


@router.post("/redeem-promo", response_model=RedeemPromoResponse)
async def redeem_promo(
    body: RedeemPromoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RedeemPromoResponse:
    from datetime import datetime, timezone
    from app.models.promo import PromoCode, PromoRedemption

    code = body.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Promo code required")

    promo = (
        await db.execute(select(PromoCode).where(PromoCode.code == code))
    ).scalar_one_or_none()

    if not promo or not promo.is_active:
        raise HTTPException(status_code=404, detail="Invalid or expired promo code")

    # Check expiry
    if promo.expires_at:
        expires = promo.expires_at
        if hasattr(expires, "tzinfo") and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(status_code=400, detail="This promo code has expired")

    # Check max uses
    if promo.max_uses > 0 and promo.current_uses >= promo.max_uses:
        raise HTTPException(status_code=400, detail="This promo code has reached its usage limit")

    # Check if already redeemed by this user
    already = (
        await db.execute(
            select(PromoRedemption).where(
                PromoRedemption.promo_code_id == promo.id,
                PromoRedemption.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if already:
        raise HTTPException(status_code=400, detail="You have already redeemed this promo code")

    # Credit user
    amount = promo.discount_kobo
    current_user.credits += amount
    promo.current_uses += 1

    db.add(PromoRedemption(promo_code_id=promo.id, user_id=current_user.id, credited_kobo=amount))
    db.add(CreditTransaction(user_id=current_user.id, amount=amount, reason="promo_code"))

    from app.services.notification_service import NotificationService
    await NotificationService(db).create(
        user_id=current_user.id,
        type="credit_received",
        title="Promo Code Redeemed",
        body=f"₦{amount // 100:,} credited from promo code {promo.code}.",
    )

    await db.commit()
    await db.refresh(current_user)

    return RedeemPromoResponse(
        ok=True,
        credited_kobo=amount,
        balance_after_kobo=int(current_user.credits),
        message=f"₦{amount // 100:,} has been added to your balance!",
    )
