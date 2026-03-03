from __future__ import annotations

import logging
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Scan
from app.services.whatsapp import WhatsAppClient, extract_inbound_messages
from app.tasks.scan_tasks import process_upload
from app.utils.storage import save_upload


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


def _get_media_id(message: dict) -> str | None:
    """Extract media_id from a WhatsApp message (image or document)."""
    mtype = message.get("type", "")
    media_obj = message.get(mtype) or {}
    return media_obj.get("id")


@router.post("/whatsapp")
async def whatsapp_incoming(payload: dict, db: AsyncSession = Depends(get_db)):
    """Incoming WhatsApp webhook messages.

    Handles text messages with instructions, and image/document messages
    by downloading the media and triggering the scan pipeline.
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
                        "Send a photo or PDF of your lab results and I'll generate a free preview. "
                        "To see the full interpretation, you'll need 1 credit.\n\n"
                        f"You said: {text}"
                    ),
                )
            elif mtype in ("image", "document"):
                media_id = _get_media_id(m)
                if not media_id:
                    await wa.send_text(to=from_, body="Could not read your file. Please try again.")
                    continue

                # Download the media file
                media_url = await wa.get_media_url(media_id=media_id)
                media_bytes = await wa.download_media(media_url=media_url)

                # Determine filename and MIME type
                media_obj = m.get(mtype) or {}
                filename = media_obj.get("filename", f"whatsapp_{media_id}")
                mime = media_obj.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"

                # Save file and create scan
                path = save_upload(filename=filename, content=media_bytes)
                scan = Scan(status="processing", input_type="upload", file_url=path, source="whatsapp")
                db.add(scan)
                await db.commit()
                await db.refresh(scan)

                # Trigger pipeline
                process_upload.delay(str(scan.id), path, mime)

                await wa.send_text(
                    to=from_,
                    body="Thanks! I received your file. Processing has started — I'll reply with a preview soon.",
                )
            else:
                await wa.send_text(
                    to=from_,
                    body="Please send a photo or PDF of your lab results.",
                )
        except Exception:
            logger.exception("Failed to process WhatsApp message")

    return {"status": "ok"}
