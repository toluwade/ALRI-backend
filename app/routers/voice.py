from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.models.voice import VoiceTranscription
from app.services.credit_manager import CreditManager
from app.services.stt import SpeechToText

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3",
    "audio/mp4", "audio/wav", "audio/x-wav", "audio/flac",
}


class TranscribeResponse(BaseModel):
    id: str
    transcription: str
    scan_id: str | None
    cost_kobo: int
    balance_kobo: int


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_voice(
    file: UploadFile = File(...),
    scan_id: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transcribe a voice note. Paid users only, costs ₦100."""

    cm = CreditManager(db)

    if not cm.is_paid_user(user):
        raise HTTPException(
            status_code=403,
            detail="Voice transcription is only available for paid users. Top up to unlock.",
        )

    mime = file.content_type or ""
    if mime not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    content = await file.read()
    if len(content) > 25 * 1024 * 1024:  # Whisper limit ~25 MB
        raise HTTPException(status_code=400, detail="Audio must be under 25 MB")

    scan_uuid = None
    if scan_id:
        try:
            scan_uuid = uuid.UUID(scan_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scan_id")

    # Create record
    record = VoiceTranscription(
        user_id=user.id,
        scan_id=scan_uuid,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    try:
        # Transcribe in-memory first (no disk storage — audio is discarded after)
        stt = SpeechToText()
        text = await stt.transcribe(content, file.filename or "audio.webm")
        record.transcription = text

        # Deduct ₦100 only after successful transcription
        await cm.deduct_for_voice(user=user, scan_id=scan_uuid)
        record.credit_deducted = True

        logger.info("Voice transcription %s completed for user %s", record.id, user.id)

    except HTTPException:
        await db.commit()
        raise
    except Exception as exc:
        await db.commit()
        logger.exception("Voice transcription %s failed: %s", record.id, exc)
        raise HTTPException(
            status_code=503,
            detail="Voice transcription is temporarily unavailable. Please try again in a moment.",
        )

    await db.commit()
    await db.refresh(user)

    return TranscribeResponse(
        id=str(record.id),
        transcription=record.transcription or "",
        scan_id=scan_id,
        cost_kobo=10_000,
        balance_kobo=user.credits,
    )
