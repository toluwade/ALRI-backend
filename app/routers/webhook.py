from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import CreditTransaction, User
from app.services.paystack import verify_transaction, verify_webhook_signature
from app.services.whatsapp import WhatsAppClient, extract_inbound_messages


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])


@router.post("/paystack")
async def paystack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Paystack webhook events.

    We credit user balance (kobo) on successful payments.
    """

    signature = request.headers.get("x-paystack-signature") or ""
    body = await request.body()

    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data") or {}

    # We only handle successful charges.
    if event not in {"charge.success"}:
        return {"status": "ignored"}

    reference = data.get("reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Missing reference")

    # Idempotency: if we've already credited this reference, skip.
    reason = f"paystack_success:{reference}"[:50]
    existing = (
        await db.execute(
            select(CreditTransaction.id).where(
                CreditTransaction.reason == reason,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return {"status": "ok", "duplicate": True}

    # Verify with Paystack for safety.
    verified = await verify_transaction(reference)
    if verified.get("status") != "success":
        raise HTTPException(status_code=400, detail="Transaction not successful")

    amount_kobo = int(verified.get("amount") or 0)
    if amount_kobo <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    metadata = verified.get("metadata") or {}
    user_id = metadata.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id metadata")

    import uuid

    try:
        uid = uuid.UUID(str(user_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.credits += amount_kobo
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=amount_kobo,
            reason=reason,
            scan_id=None,
        )
    )
    await db.commit()

    return {"status": "ok"}


@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta webhook verification.

    Expects query params:
    - hub.mode
    - hub.verify_token
    - hub.challenge
    """

    qp = request.query_params
    mode = qp.get("hub.mode")
    token = qp.get("hub.verify_token")
    challenge = qp.get("hub.challenge")

    if mode == "subscribe" and token and token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(challenge) if challenge is not None and challenge.isdigit() else (challenge or "")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp")
async def whatsapp_incoming(payload: dict):
    """Incoming WhatsApp webhook messages.

    This handler is intentionally lightweight. It extracts inbound messages and
    responds with a basic acknowledgement. Media handling / scan triggering is
    implemented in services and Celery tasks.
    """

    msgs = extract_inbound_messages(payload)
    if not msgs:
        return {"status": "ignored"}

    wa = WhatsAppClient()

    for m in msgs:
        from_ = m.get("from")
        mtype = m.get("type")

        try:
            if mtype == "text":
                text = (m.get("text") or {}).get("body") or ""
                await wa.send_text(
                    to=from_,
                    body=(
                        "Send a photo or PDF of your lab results and I’ll generate a free preview. "
                        "To see the full interpretation, you’ll need 1 credit.\n\n"
                        f"You said: {text}"
                    ),
                )
            else:
                await wa.send_text(
                    to=from_,
                    body="Thanks! I received your file. Processing has started — I’ll reply with a preview soon.",
                )
        except Exception:
            logger.exception("Failed to process WhatsApp message")

    return {"status": "ok"}
