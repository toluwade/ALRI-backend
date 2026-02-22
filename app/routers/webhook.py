from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.services.whatsapp import WhatsAppClient, extract_inbound_messages


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])


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
