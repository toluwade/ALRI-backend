from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import ChatMessage, Interpretation, Marker, Scan, User
from app.services.credit_manager import CreditManager
from app.services.llm.kimi import KimiProvider
from app.services.ocr.tesseract import TesseractOCR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan", tags=["chat"])


class ChatSendRequest(BaseModel):
    message: str


class ChatSendResponse(BaseModel):
    message: str
    remaining_messages: int
    cost_kobo: int
    balance_kobo: int


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ChatLimitsResponse(BaseModel):
    max_messages: int
    char_limit: int
    cost_per_message_kobo: int
    is_paid_user: bool
    used_messages: int


# ------------------------------------------------------------------
# GET /scan/{scan_id}/chat/limits  — tier info for the frontend
# ------------------------------------------------------------------


@router.get("/{scan_id}/chat/limits", response_model=ChatLimitsResponse)
async def get_chat_limits(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    is_paid = CreditManager.is_paid_user(user)

    used = (
        await db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.scan_id == scan_id,
                ChatMessage.user_id == user.id,
                ChatMessage.role == "user",
            )
        )
    ).scalar_one()

    max_msgs = 999_999 if is_paid else settings.CHAT_MSG_LIMIT_FREE

    return ChatLimitsResponse(
        max_messages=max_msgs,
        char_limit=settings.CHAT_CHAR_LIMIT_PAID if is_paid else settings.CHAT_CHAR_LIMIT_FREE,
        cost_per_message_kobo=settings.PRICE_CHAT_MESSAGE_KOBO,
        is_paid_user=is_paid,
        used_messages=int(used),
    )


# ------------------------------------------------------------------
# GET /scan/{scan_id}/chat  — chat history
# ------------------------------------------------------------------


@router.get("/{scan_id}/chat", response_model=list[ChatMessageOut])
async def get_chat_history(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    msgs = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.scan_id == scan_id, ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()

    return [
        ChatMessageOut(
            id=str(m.id),
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat() if hasattr(m.created_at, "isoformat") else str(m.created_at),
        )
        for m in msgs
    ]


# ------------------------------------------------------------------
# POST /scan/{scan_id}/chat  — send message (₦50 per message)
# ------------------------------------------------------------------


@router.post("/{scan_id}/chat", response_model=ChatSendResponse)
async def send_chat_message(
    scan_id: uuid.UUID,
    message: str = Form(...),
    file: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSendResponse:
    msg = (message or "").strip()
    if not msg and not file:
        raise HTTPException(status_code=400, detail="message is required")

    cm = CreditManager(db)
    is_paid = cm.is_paid_user(user)

    # Character limit based on tier
    char_limit = settings.CHAT_CHAR_LIMIT_PAID if is_paid else settings.CHAT_CHAR_LIMIT_FREE
    if len(msg) > char_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Message exceeds {char_limit} character limit",
        )

    # File attachments are PRO-only
    if file and not is_paid:
        raise HTTPException(status_code=403, detail="File attachments require a paid account")

    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if scan.status != "completed":
        raise HTTPException(status_code=409, detail="Scan not completed")

    # Message limit check
    used = (
        await db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.scan_id == scan_id,
                ChatMessage.user_id == user.id,
                ChatMessage.role == "user",
            )
        )
    ).scalar_one()

    max_messages = 999_999 if is_paid else settings.CHAT_MSG_LIMIT_FREE
    if int(used) >= max_messages:
        raise HTTPException(
            status_code=429,
            detail="Message limit reached for this report. Top up to unlock unlimited messages.",
        )

    # If file attached, run OCR to extract text (in-memory, no disk storage)
    file_context = ""
    if file:
        try:
            file_bytes = await file.read()
            mime = file.content_type or "application/octet-stream"
            ocr = TesseractOCR()
            extracted_text = await ocr.extract_text(
                file_bytes=file_bytes,
                filename=file.filename or "",
                mime_type=mime,
            )
            if extracted_text and extracted_text.strip():
                file_context = f"\n\n[USER ATTACHED AN IMAGE — extracted text from image:\n{extracted_text.strip()}\n]"
                logger.info("Chat file OCR extracted %d chars for scan %s", len(extracted_text), scan_id)
            else:
                file_context = "\n\n[USER ATTACHED AN IMAGE but no text could be extracted from it]"
        except Exception as e:
            logger.warning("Chat file OCR failed for scan %s: %s", scan_id, e)
            file_context = "\n\n[USER ATTACHED AN IMAGE but OCR failed to process it]"

    # Deduct ₦50 for this message
    await cm.deduct_for_chat(user=user, scan_id=scan_id)

    # Load context: markers + interpretation
    markers = (
        await db.execute(select(Marker).where(Marker.scan_id == scan_id).order_by(Marker.created_at.asc()))
    ).scalars().all()
    interp = (
        await db.execute(select(Interpretation).where(Interpretation.scan_id == scan_id))
    ).scalar_one_or_none()

    context_lines = ["FULL REPORT CONTEXT (lab markers + interpretation):"]
    for m in markers:
        context_lines.append(
            f"- {m.name}: {m.value} {m.unit or ''} (ref {m.reference_low}-{m.reference_high}), status={m.status}. {m.explanation or ''}".strip()
        )
    if interp and interp.summary:
        context_lines.append(f"\nSUMMARY: {interp.summary}")
    if interp and isinstance(interp.correlations, list) and interp.correlations:
        context_lines.append("\nCORRELATIONS:")
        for c in interp.correlations:
            context_lines.append(f"- {c}")

    context = "\n".join(context_lines)

    # Chat history
    history = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.scan_id == scan_id, ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()

    llm_messages = [{"role": h.role, "content": h.content} for h in history]
    # Include file context in the LLM message so AI can reference the attached image's content
    llm_messages.append({"role": "user", "content": msg + file_context})

    provider = KimiProvider()
    assistant_text = await provider.chat(messages=llm_messages, scan_context=context)

    # Store only the user's text in DB (not OCR output — keeps messages clean)
    stored_msg = msg if not file else f"{msg}\n📎 Image attached" if msg else "📎 Image attached"
    user_row = ChatMessage(scan_id=scan_id, user_id=user.id, role="user", content=stored_msg)
    assistant_row = ChatMessage(scan_id=scan_id, user_id=user.id, role="assistant", content=assistant_text)
    db.add_all([user_row, assistant_row])
    await db.commit()

    remaining = max_messages - (int(used) + 1)
    return ChatSendResponse(
        message=assistant_text,
        remaining_messages=remaining,
        cost_kobo=settings.PRICE_CHAT_MESSAGE_KOBO,
        balance_kobo=user.credits,
    )
