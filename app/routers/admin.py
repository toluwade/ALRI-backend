"""Admin router — platform management endpoints.

All endpoints require an authenticated user with is_admin=True.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_admin_user
from app.models import CreditTransaction, PromoCode, PromoRedemption, Scan, User
from app.models.tariff import Tariff
from app.schemas.admin import (
    AdminScanItem,
    AdminScanListResponse,
    AdminStatsResponse,
    AdminTransactionItem,
    AdminTransactionListResponse,
    AdminUserDetail,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserScanItem,
    AdminUserTransactionItem,
    AdminUserUpdate,
    PromoCodeCreate,
    PromoCodeListResponse,
    PromoCodeResponse,
    PromoCodeUpdate,
    TariffResponse,
    TariffUpdate,
)
from app.services.tariff_loader import get_tariffs

router = APIRouter(prefix="/admin", tags=["admin"])


# Reuse reason classification from user router
_REASON_MAP: dict[str, tuple[str, str]] = {
    "scan_used": ("deduction", "Scan Unlock"),
    "chat_used": ("deduction", "Chat Message"),
    "skin_analysis": ("deduction", "Skin Analysis"),
    "voice_used": ("deduction", "Voice Transcription"),
    "file_upload": ("deduction", "File Upload"),
    "grant": ("reward", "Credit Bonus"),
    "signup_bonus": ("reward", "Signup Bonus"),
    "promo_code": ("reward", "Promo Code"),
}


def _classify_reason(reason: str, amount: int) -> tuple[str, str]:
    if reason in _REASON_MAP:
        return _REASON_MAP[reason]
    if reason.startswith("paystack_success:"):
        return ("topup", "Paystack Top-up")
    if reason.startswith("paystack_init:"):
        return ("init", "Payment Initiated")
    if "referral" in reason.lower():
        return ("reward", "Referral Reward")
    return ("reward" if amount > 0 else "deduction", reason.replace("_", " ").title())


# ── Stats ──────────────────────────────────────────────

@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    total_scans = (await db.execute(select(func.count()).select_from(Scan))).scalar_one()

    # Revenue = sum of all successful paystack top-ups
    total_revenue = (
        await db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.reason.startswith("paystack_success:")
            )
        )
    ).scalar_one()

    active_users_7d = (
        await db.execute(
            select(func.count(func.distinct(CreditTransaction.user_id))).where(
                CreditTransaction.created_at >= week_ago
            )
        )
    ).scalar_one()

    new_users_7d = (
        await db.execute(
            select(func.count()).select_from(User).where(User.created_at >= week_ago)
        )
    ).scalar_one()

    # Total bonuses = sum of all signup_bonus transactions
    total_bonuses = (
        await db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.reason == "signup_bonus"
            )
        )
    ).scalar_one()

    return AdminStatsResponse(
        total_users=int(total_users),
        total_scans=int(total_scans),
        total_revenue_kobo=int(total_revenue),
        total_bonuses_kobo=int(total_bonuses),
        active_users_7d=int(active_users_7d),
        new_users_7d=int(new_users_7d),
    )


# ── Users ──────────────────────────────────────────────

@router.get("/users", response_model=AdminUserListResponse)
async def admin_list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    base = select(User)
    count_base = select(func.count()).select_from(User)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(User.email.ilike(pattern), User.name.ilike(pattern))
        base = base.where(search_filter)
        count_base = count_base.where(search_filter)

    total = (await db.execute(count_base)).scalar_one()

    offset = (page - 1) * per_page
    users = (
        await db.execute(base.order_by(User.created_at.desc()).offset(offset).limit(per_page))
    ).scalars().all()

    items = []
    for u in users:
        scan_count = (
            await db.execute(select(func.count()).select_from(Scan).where(Scan.user_id == u.id))
        ).scalar_one()
        items.append(
            AdminUserItem(
                id=str(u.id),
                email=u.email,
                name=u.name,
                credits=u.credits,
                credits_naira=u.credits / 100.0,
                scan_count=int(scan_count),
                has_topped_up=u.has_topped_up,
                is_admin=u.is_admin,
                created_at=u.created_at.isoformat() if hasattr(u.created_at, "isoformat") else str(u.created_at),
            )
        )

    return AdminUserListResponse(users=items, total=int(total), page=page, per_page=per_page)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def admin_get_user(
    user_id: uuid.UUID,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetail:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Recent scans
    scans = (
        await db.execute(
            select(Scan).where(Scan.user_id == user.id).order_by(Scan.created_at.desc()).limit(20)
        )
    ).scalars().all()

    # Recent transactions
    txns = (
        await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user.id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    return AdminUserDetail(
        id=str(user.id),
        email=user.email,
        phone=user.phone,
        name=user.name,
        avatar_url=user.avatar_url,
        auth_provider=user.auth_provider,
        age=user.age,
        sex=user.sex,
        credits=user.credits,
        credits_naira=user.credits / 100.0,
        has_topped_up=user.has_topped_up,
        is_admin=user.is_admin,
        created_at=user.created_at.isoformat() if hasattr(user.created_at, "isoformat") else str(user.created_at),
        scans=[
            AdminUserScanItem(
                id=str(s.id),
                status=s.status or "processing",
                input_type=s.input_type,
                source=s.source,
                created_at=s.created_at.isoformat() if hasattr(s.created_at, "isoformat") else str(s.created_at),
            )
            for s in scans
        ],
        transactions=[
            AdminUserTransactionItem(
                id=str(tx.id),
                amount=tx.amount,
                amount_naira=tx.amount / 100.0,
                reason=tx.reason,
                created_at=tx.created_at.isoformat() if hasattr(tx.created_at, "isoformat") else str(tx.created_at),
            )
            for tx in txns
        ],
    )


@router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.is_admin is not None:
        user.is_admin = body.is_admin

    if body.credits_adjustment_kobo is not None and body.credits_adjustment_kobo != 0:
        user.credits += body.credits_adjustment_kobo
        if user.credits < 0:
            user.credits = 0
        db.add(
            CreditTransaction(
                user_id=user.id,
                amount=body.credits_adjustment_kobo,
                reason=f"admin_adjustment_by_{admin.email or admin.id}",
            )
        )

    await db.commit()
    await db.refresh(user)
    return {"ok": True, "credits": user.credits, "is_admin": user.is_admin}


# ── Transactions ───────────────────────────────────────

@router.get("/transactions", response_model=AdminTransactionListResponse)
async def admin_list_transactions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    reason: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminTransactionListResponse:
    filters = [~CreditTransaction.reason.startswith("paystack_init:")]

    if reason:
        filters.append(CreditTransaction.reason == reason)
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            filters.append(CreditTransaction.created_at >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            filters.append(CreditTransaction.created_at <= dt)
        except ValueError:
            pass

    total = (
        await db.execute(select(func.count()).select_from(CreditTransaction).where(*filters))
    ).scalar_one()

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            select(CreditTransaction)
            .where(*filters)
            .order_by(CreditTransaction.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
    ).scalars().all()

    # Batch-load user emails
    user_ids = list({tx.user_id for tx in rows})
    user_map: dict[uuid.UUID, str | None] = {}
    if user_ids:
        users = (await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all()
        user_map = {uid: email for uid, email in users}

    items = []
    for tx in rows:
        cat, label = _classify_reason(tx.reason, tx.amount)
        items.append(
            AdminTransactionItem(
                id=str(tx.id),
                user_id=str(tx.user_id),
                user_email=user_map.get(tx.user_id),
                amount=tx.amount,
                amount_naira=tx.amount / 100.0,
                reason=tx.reason,
                category=cat,
                label=label,
                scan_id=str(tx.scan_id) if tx.scan_id else None,
                created_at=tx.created_at.isoformat() if hasattr(tx.created_at, "isoformat") else str(tx.created_at),
            )
        )

    return AdminTransactionListResponse(
        transactions=items, total=int(total), page=page, per_page=per_page
    )


# ── Scans ──────────────────────────────────────────────

@router.get("/scans", response_model=AdminScanListResponse)
async def admin_list_scans(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminScanListResponse:
    filters = []
    if status:
        filters.append(Scan.status == status)

    total = (
        await db.execute(select(func.count()).select_from(Scan).where(*filters) if filters else select(func.count()).select_from(Scan))
    ).scalar_one()

    offset = (page - 1) * per_page
    query = select(Scan).order_by(Scan.created_at.desc()).offset(offset).limit(per_page)
    if filters:
        query = query.where(*filters)
    scans = (await db.execute(query)).scalars().all()

    # Batch-load user emails
    user_ids = list({s.user_id for s in scans if s.user_id})
    user_map: dict[uuid.UUID, str | None] = {}
    if user_ids:
        users = (await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all()
        user_map = {uid: email for uid, email in users}

    items = [
        AdminScanItem(
            id=str(s.id),
            user_id=str(s.user_id) if s.user_id else "",
            user_email=user_map.get(s.user_id) if s.user_id else None,
            status=s.status or "processing",
            input_type=s.input_type,
            source=s.source,
            full_unlocked=s.full_unlocked,
            created_at=s.created_at.isoformat() if hasattr(s.created_at, "isoformat") else str(s.created_at),
        )
        for s in scans
    ]

    return AdminScanListResponse(scans=items, total=int(total), page=page, per_page=per_page)


# ── Promo Codes ────────────────────────────────────────

def _promo_to_response(p: PromoCode) -> PromoCodeResponse:
    return PromoCodeResponse(
        id=str(p.id),
        code=p.code,
        discount_kobo=p.discount_kobo,
        discount_naira=p.discount_kobo / 100.0,
        max_uses=p.max_uses,
        current_uses=p.current_uses,
        is_active=p.is_active,
        created_by=str(p.created_by) if p.created_by else None,
        expires_at=p.expires_at.isoformat() if p.expires_at and hasattr(p.expires_at, "isoformat") else None,
        created_at=p.created_at.isoformat() if hasattr(p.created_at, "isoformat") else str(p.created_at),
    )


@router.get("/promo-codes", response_model=PromoCodeListResponse)
async def admin_list_promo_codes(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> PromoCodeListResponse:
    promos = (
        await db.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
    ).scalars().all()
    return PromoCodeListResponse(
        promo_codes=[_promo_to_response(p) for p in promos],
        total=len(promos),
    )


@router.post("/promo-codes", response_model=PromoCodeResponse)
async def admin_create_promo_code(
    body: PromoCodeCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> PromoCodeResponse:
    # Check uniqueness
    existing = (
        await db.execute(select(PromoCode).where(PromoCode.code == body.code.upper()))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Promo code already exists")

    expires_at = None
    if body.expires_at:
        try:
            expires_at = datetime.fromisoformat(body.expires_at).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format")

    promo = PromoCode(
        code=body.code.upper(),
        discount_kobo=body.discount_kobo,
        max_uses=body.max_uses,
        created_by=admin.id,
        expires_at=expires_at,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return _promo_to_response(promo)


@router.patch("/promo-codes/{promo_id}", response_model=PromoCodeResponse)
async def admin_update_promo_code(
    promo_id: uuid.UUID,
    body: PromoCodeUpdate,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> PromoCodeResponse:
    promo = (await db.execute(select(PromoCode).where(PromoCode.id == promo_id))).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")

    if body.is_active is not None:
        promo.is_active = body.is_active
    if body.max_uses is not None:
        promo.max_uses = body.max_uses
    if body.expires_at is not None:
        try:
            promo.expires_at = datetime.fromisoformat(body.expires_at).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format")

    await db.commit()
    await db.refresh(promo)
    return _promo_to_response(promo)


@router.delete("/promo-codes/{promo_id}")
async def admin_delete_promo_code(
    promo_id: uuid.UUID,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    promo = (await db.execute(select(PromoCode).where(PromoCode.id == promo_id))).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")
    promo.is_active = False
    await db.commit()
    return {"ok": True}


# ── Tariffs ───────────────────────────────────────────

def _tariff_to_response(t: Tariff) -> TariffResponse:
    return TariffResponse(
        signup_bonus_kobo=t.signup_bonus_kobo,
        referral_bonus_kobo=t.referral_bonus_kobo,
        cost_per_chat_kobo=t.cost_per_chat_kobo,
        cost_per_file_upload_kobo=t.cost_per_file_upload_kobo,
        cost_per_transcription_kobo=t.cost_per_transcription_kobo,
        cost_per_scan_unlock_kobo=t.cost_per_scan_unlock_kobo,
        cost_per_skin_analysis_kobo=t.cost_per_skin_analysis_kobo,
        signup_bonus_naira=t.signup_bonus_kobo / 100.0,
        referral_bonus_naira=t.referral_bonus_kobo / 100.0,
        cost_per_chat_naira=t.cost_per_chat_kobo / 100.0,
        cost_per_file_upload_naira=t.cost_per_file_upload_kobo / 100.0,
        cost_per_transcription_naira=t.cost_per_transcription_kobo / 100.0,
        cost_per_scan_unlock_naira=t.cost_per_scan_unlock_kobo / 100.0,
        cost_per_skin_analysis_naira=t.cost_per_skin_analysis_kobo / 100.0,
    )


@router.get("/tariffs", response_model=TariffResponse)
async def admin_get_tariffs(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TariffResponse:
    tariff = await get_tariffs(db)
    return _tariff_to_response(tariff)


@router.put("/tariffs", response_model=TariffResponse)
async def admin_update_tariffs(
    body: TariffUpdate,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> TariffResponse:
    tariff = await get_tariffs(db)

    for field in (
        "signup_bonus_kobo",
        "referral_bonus_kobo",
        "cost_per_chat_kobo",
        "cost_per_file_upload_kobo",
        "cost_per_transcription_kobo",
        "cost_per_scan_unlock_kobo",
        "cost_per_skin_analysis_kobo",
    ):
        value = getattr(body, field, None)
        if value is not None:
            setattr(tariff, field, value)

    await db.commit()
    await db.refresh(tariff)
    return _tariff_to_response(tariff)
