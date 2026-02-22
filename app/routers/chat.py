from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import ChatMessage, Interpretation, Marker, Scan, User
from app.services.llm.kimi import KimiProvider

router = APIRouter(prefix="/scan", tags=["chat"])

MAX_MESSAGES_PER_SCAN = 10


class ChatSendRequest(BaseModel):
    message: str


class ChatSendResponse(BaseModel):
    message: str
    remaining_messages: int


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


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


@router.post("/{scan_id}/chat", response_model=ChatSendResponse)
async def send_chat_message(
    scan_id: uuid.UUID,
    body: ChatSendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSendResponse:
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message is required")

    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if scan.status != "completed":
        raise HTTPException(status_code=409, detail="Scan not completed")

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

    if int(used) >= MAX_MESSAGES_PER_SCAN:
        raise HTTPException(status_code=429, detail="Message limit reached for this report")

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

    # History
    history = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.scan_id == scan_id, ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()

    llm_messages = [{"role": h.role, "content": h.content} for h in history]
    llm_messages.append({"role": "user", "content": msg})

    provider = KimiProvider()
    assistant_text = await provider.chat(messages=llm_messages, scan_context=context)

    user_row = ChatMessage(scan_id=scan_id, user_id=user.id, role="user", content=msg)
    assistant_row = ChatMessage(scan_id=scan_id, user_id=user.id, role="assistant", content=assistant_text)
    db.add_all([user_row, assistant_row])
    await db.commit()

    remaining = MAX_MESSAGES_PER_SCAN - (int(used) + 1)
    return ChatSendResponse(message=assistant_text, remaining_messages=remaining)
