"""Multi-currency payments router.

- GET /payments/packages?currency=USD          — list active packages + prices
- POST /payments/checkout                      — create a provider invoice/session
- POST /webhook/paystack                       — Paystack IPN
- POST /webhook/stripe                         — Stripe events
- POST /webhook/nowpayments                    — NOWPayments IPN
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.payment import Payment, TopUpPackage
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.credit_manager import CreditManager
from app.services.payments import (
    PaymentStatus,
    UnsupportedCurrencyError,
    get_provider,
)
from app.services.payments.registry import available_providers, provider_for_currency
from app.services.pricing import (
    SUPPORTED_CURRENCIES,
    currency_for_country,
    get_package_price,
    list_packages_for_currency,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])
webhook_router = APIRouter(prefix="/webhook", tags=["webhooks"])


class PackageResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    credits_granted: int
    is_popular: bool = False
    currency: str
    amount_minor: int


class PackagesResponse(BaseModel):
    currency: str
    packages: list[PackageResponse]
    available_providers: list[str]


class CheckoutRequest(BaseModel):
    package_code: str = Field(..., description="starter | pro | power")
    currency: str = Field(..., description="NGN | USD | EUR | GBP | USDT")
    pay_currency: str | None = Field(
        None, description="For crypto: usdterc20 | usdttrc20"
    )


class CheckoutResponse(BaseModel):
    reference: str
    provider: str
    checkout_url: str | None
    extra: dict


@router.get("/packages", response_model=PackagesResponse)
async def packages(
    currency: str | None = None,
    cf_ipcountry: str | None = Header(default=None, alias="CF-IPCountry"),
    db: AsyncSession = Depends(get_db),
) -> PackagesResponse:
    """List top-up packages with localized prices.

    Currency resolution order:
    1. Explicit `?currency=` query param
    2. Cloudflare `CF-IPCountry` header -> mapped currency
    3. USD fallback
    """
    resolved_currency = (currency or currency_for_country(cf_ipcountry)).upper()
    if resolved_currency not in SUPPORTED_CURRENCIES:
        resolved_currency = "USD"

    rows = await list_packages_for_currency(db, resolved_currency)
    return PackagesResponse(
        currency=resolved_currency,
        packages=[PackageResponse(**r) for r in rows],
        available_providers=available_providers(),
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    currency = body.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Unsupported currency: {currency}")

    price = await get_package_price(db, body.package_code, currency)
    if not price:
        raise HTTPException(status_code=404, detail="Package or price not found")

    try:
        provider = provider_for_currency(currency)
    except UnsupportedCurrencyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    reference = f"alri_{provider.code}_{current_user.id.hex}_{uuid.uuid4().hex[:12]}"
    metadata = {
        "user_id": str(current_user.id),
        "package_code": body.package_code,
        "package_name": price["name"],
        "credits_granted": price["credits_granted"],
    }
    if body.pay_currency:
        metadata["pay_currency"] = body.pay_currency

    # Persist pending payment BEFORE calling provider (so webhook can find it)
    payment = Payment(
        user_id=current_user.id,
        package_id=price["id"],
        provider=provider.code,
        provider_reference=reference,
        currency=currency,
        amount_minor=price["amount_minor"],
        status=PaymentStatus.PENDING.value,
        credits_granted=price["credits_granted"],
        extra=metadata,
    )
    db.add(payment)
    await db.commit()

    try:
        result = await provider.create_invoice(
            reference=reference,
            user_email=current_user.email,
            amount_minor=price["amount_minor"],
            currency=currency,
            metadata=metadata,
        )
    except UnsupportedCurrencyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Provider invoice creation failed: %s", provider.code)
        payment.status = PaymentStatus.FAILED.value
        payment.extra = {**(payment.extra or {}), "error": str(e)}
        await db.commit()
        raise HTTPException(status_code=502, detail="Payment provider error") from e

    # Record provider's session/invoice id if different from our reference
    extra = {**(payment.extra or {}), **result.extra}
    if result.checkout_url:
        extra["checkout_url"] = result.checkout_url
    payment.extra = extra
    await db.commit()

    return CheckoutResponse(
        reference=reference,
        provider=provider.code,
        checkout_url=result.checkout_url,
        extra=result.extra,
    )


async def _complete_payment(
    db: AsyncSession,
    payment: Payment,
    verification_extra: dict | None = None,
) -> None:
    """Mark payment succeeded and credit the user (idempotent)."""
    if payment.status == PaymentStatus.SUCCEEDED.value:
        return

    payment.status = PaymentStatus.SUCCEEDED.value
    payment.completed_at = datetime.now(timezone.utc)
    if verification_extra:
        payment.extra = {**(payment.extra or {}), "verification": verification_extra}

    user_result = await db.execute(select(User).where(User.id == payment.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        logger.error("Payment %s completed but user %s not found", payment.id, payment.user_id)
        await db.commit()
        return

    if not user.has_topped_up:
        user.has_topped_up = True

    await db.commit()

    await CreditManager(db).grant(
        user=user,
        amount=payment.credits_granted,
        reason=f"{payment.provider}_success:{payment.provider_reference}",
    )

    # Referral reward: idempotently credit the referrer once per referee,
    # triggered by any successful top-up. Repeats are no-ops.
    try:
        from app.services.referral import award_referral_bonus_if_first_topup
        await award_referral_bonus_if_first_topup(db, user)
    except Exception as e:
        logger.warning("Referral bonus check failed for user %s: %s", user.id, e)


@webhook_router.post("/paystack")
async def paystack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    provider = get_provider("paystack")
    if not provider.verify_webhook_signature(payload=raw, headers=dict(request.headers)):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(raw)
    if event.get("event") != "charge.success":
        return {"ok": True, "ignored": event.get("event")}

    data = event["data"]
    reference = data.get("reference")
    if not reference:
        return {"ok": True, "note": "no reference"}

    result = await db.execute(select(Payment).where(Payment.provider_reference == reference))
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning("Paystack webhook for unknown reference: %s", reference)
        return {"ok": True, "note": "unknown reference"}

    await _complete_payment(
        db,
        payment,
        {"gateway_response": data.get("gateway_response"), "channel": data.get("channel")},
    )
    return {"ok": True}


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    provider = get_provider("stripe")
    if not provider.verify_webhook_signature(payload=raw, headers=dict(request.headers)):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(raw)
    etype = event.get("type")
    if etype != "checkout.session.completed":
        return {"ok": True, "ignored": etype}

    session = event["data"]["object"]
    reference = session.get("client_reference_id") or (session.get("metadata") or {}).get("reference")
    if not reference:
        return {"ok": True, "note": "no reference"}

    result = await db.execute(select(Payment).where(Payment.provider_reference == reference))
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning("Stripe webhook for unknown reference: %s", reference)
        return {"ok": True, "note": "unknown reference"}

    if session.get("payment_status") != "paid":
        return {"ok": True, "note": f"payment_status={session.get('payment_status')}"}

    await _complete_payment(
        db,
        payment,
        {"session_id": session.get("id"), "payment_intent": session.get("payment_intent")},
    )
    return {"ok": True}


@webhook_router.post("/nowpayments")
async def nowpayments_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    provider = get_provider("nowpayments")
    if not provider.verify_webhook_signature(payload=raw, headers=dict(request.headers)):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = json.loads(raw)
    order_id = data.get("order_id")
    payment_status = data.get("payment_status")
    if not order_id:
        return {"ok": True, "note": "no order_id"}

    result = await db.execute(select(Payment).where(Payment.provider_reference == order_id))
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning("NOWPayments webhook for unknown order_id: %s", order_id)
        return {"ok": True, "note": "unknown order_id"}

    if payment_status in {"finished", "confirmed"}:
        await _complete_payment(
            db,
            payment,
            {"payment_id": data.get("payment_id"), "actually_paid": data.get("actually_paid")},
        )
    elif payment_status in {"failed", "expired"}:
        payment.status = PaymentStatus.FAILED.value
        payment.extra = {**(payment.extra or {}), "webhook_status": payment_status}
        await db.commit()

    return {"ok": True}
