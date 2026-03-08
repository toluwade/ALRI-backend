from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.models.skin_analysis import SkinAnalysis
from app.models.skin_chat import SkinChatMessage
from app.services.credit_manager import CreditManager
from app.services.llm.kimi import KimiProvider
from app.services.skin_analyzer import SkinAnalyzer
from app.services.skin_report_generator import SkinReportGenerator
from app.utils.storage import save_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skin", tags=["skin"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------


class SkinAnalysisResponse(BaseModel):
    id: str
    status: str
    analysis: dict | None
    cost_kobo: int
    balance_kobo: int


class SkinAnalysisListItem(BaseModel):
    id: str
    status: str
    severity: str | None
    condition_names: list[str]
    created_at: str


class SkinAnalysisListResponse(BaseModel):
    analyses: list[SkinAnalysisListItem]
    total: int
    page: int
    per_page: int


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


class ChatSendResponse(BaseModel):
    message: str
    remaining_messages: int
    cost_kobo: int
    balance_kobo: int


# ------------------------------------------------------------------
# POST /skin/analyze  — upload + analyse (₦250)
# ------------------------------------------------------------------


@router.post("/analyze", response_model=SkinAnalysisResponse)
async def analyze_skin(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload skin image for AI analysis. Paid users only, costs ₦250."""

    cm = CreditManager(db)

    if not cm.is_paid_user(user):
        raise HTTPException(
            status_code=403,
            detail="Skin analysis is only available for paid users. Top up your account to unlock.",
        )

    mime = file.content_type or ""
    if mime not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only image files (JPEG, PNG, WebP, HEIC) are supported")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 10 MB")

    # Create record
    analysis = SkinAnalysis(user_id=user.id, status="processing")
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    try:
        # Deduct ₦250
        await cm.deduct_for_skin_analysis(user=user)
        analysis.credit_deducted = True

        # Save file
        file_path = save_upload(
            filename=f"skin_{analysis.id.hex}_{file.filename or 'image.jpg'}",
            content=content,
        )
        analysis.image_url = file_path

        # Run AI analysis
        analyzer = SkinAnalyzer()
        result = await analyzer.analyze(content, mime)

        analysis.analysis_result = result
        analysis.status = "completed"
        logger.info("Skin analysis %s completed for user %s", analysis.id, user.id)

    except HTTPException:
        analysis.status = "failed"
        await db.commit()
        raise
    except Exception as exc:
        analysis.status = "failed"
        await db.commit()
        logger.exception("Skin analysis %s failed: %s", analysis.id, exc)
        raise HTTPException(status_code=500, detail="Analysis failed. Please try again.")

    await db.commit()
    await db.refresh(user)

    return SkinAnalysisResponse(
        id=str(analysis.id),
        status=analysis.status,
        analysis=analysis.analysis_result,
        cost_kobo=25_000,
        balance_kobo=user.credits,
    )


# ------------------------------------------------------------------
# GET /skin/analyses  — list user's skin analyses (paginated)
# ------------------------------------------------------------------


@router.get("/analyses", response_model=SkinAnalysisListResponse)
async def list_skin_analyses(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total = (
        await db.execute(
            select(func.count()).select_from(SkinAnalysis).where(SkinAnalysis.user_id == user.id)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(SkinAnalysis)
            .where(SkinAnalysis.user_id == user.id)
            .order_by(SkinAnalysis.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    items = []
    for r in rows:
        result = r.analysis_result or {}
        items.append(
            SkinAnalysisListItem(
                id=str(r.id),
                status=r.status,
                severity=result.get("severity") if isinstance(result, dict) else None,
                condition_names=[
                    c.get("name", "") for c in (result.get("conditions") or [])
                ] if isinstance(result, dict) else [],
                created_at=r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
            )
        )

    return SkinAnalysisListResponse(analyses=items, total=int(total), page=page, per_page=per_page)


# ------------------------------------------------------------------
# GET /skin/{analysis_id}  — retrieve a past analysis
# ------------------------------------------------------------------


@router.get("/{analysis_id}", response_model=SkinAnalysisResponse)
async def get_skin_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analysis = (
        await db.execute(select(SkinAnalysis).where(SkinAnalysis.id == analysis_id))
    ).scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return SkinAnalysisResponse(
        id=str(analysis.id),
        status=analysis.status,
        analysis=analysis.analysis_result,
        cost_kobo=25_000,
        balance_kobo=user.credits,
    )


# ------------------------------------------------------------------
# DELETE /skin/{analysis_id}  — delete an analysis + chat history
# ------------------------------------------------------------------


@router.delete("/{analysis_id}")
async def delete_skin_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analysis = (
        await db.execute(select(SkinAnalysis).where(SkinAnalysis.id == analysis_id))
    ).scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Delete chat messages first (FK constraint)
    await db.execute(
        delete(SkinChatMessage).where(SkinChatMessage.skin_analysis_id == analysis_id)
    )

    # Delete local image file if exists
    if analysis.image_url:
        try:
            os.unlink(analysis.image_url)
        except OSError:
            pass

    await db.delete(analysis)
    await db.commit()

    return {"ok": True}


# ------------------------------------------------------------------
# GET /skin/{analysis_id}/report  — download PDF report
# ------------------------------------------------------------------


@router.get("/{analysis_id}/report")
async def get_skin_report(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analysis = (
        await db.execute(select(SkinAnalysis).where(SkinAnalysis.id == analysis_id))
    ).scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not analysis.analysis_result:
        raise HTTPException(status_code=409, detail="Analysis has no results")

    gen = SkinReportGenerator()
    pdf_bytes = gen.generate_pdf(
        analysis_id=analysis.id,
        analysis_result=analysis.analysis_result,
        created_at=analysis.created_at,
        user_name=getattr(user, "name", None),
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ALRI-Skin-Report-{str(analysis.id)[:8]}.pdf"',
        },
    )


# ------------------------------------------------------------------
# GET /skin/{analysis_id}/chat/limits  — tier info
# ------------------------------------------------------------------


@router.get("/{analysis_id}/chat/limits", response_model=ChatLimitsResponse)
async def get_skin_chat_limits(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analysis = (
        await db.execute(select(SkinAnalysis).where(SkinAnalysis.id == analysis_id))
    ).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    is_paid = CreditManager.is_paid_user(user)

    used = (
        await db.execute(
            select(func.count())
            .select_from(SkinChatMessage)
            .where(
                SkinChatMessage.skin_analysis_id == analysis_id,
                SkinChatMessage.user_id == user.id,
                SkinChatMessage.role == "user",
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
# GET /skin/{analysis_id}/chat  — chat history
# ------------------------------------------------------------------


@router.get("/{analysis_id}/chat", response_model=list[ChatMessageOut])
async def get_skin_chat_history(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analysis = (
        await db.execute(select(SkinAnalysis).where(SkinAnalysis.id == analysis_id))
    ).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    msgs = (
        await db.execute(
            select(SkinChatMessage)
            .where(SkinChatMessage.skin_analysis_id == analysis_id, SkinChatMessage.user_id == user.id)
            .order_by(SkinChatMessage.created_at.asc())
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
# POST /skin/{analysis_id}/chat  — send message (₦50)
# ------------------------------------------------------------------


@router.post("/{analysis_id}/chat", response_model=ChatSendResponse)
async def send_skin_chat_message(
    analysis_id: uuid.UUID,
    message: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    msg = (message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message is required")

    cm = CreditManager(db)
    is_paid = cm.is_paid_user(user)

    char_limit = settings.CHAT_CHAR_LIMIT_PAID if is_paid else settings.CHAT_CHAR_LIMIT_FREE
    if len(msg) > char_limit:
        raise HTTPException(status_code=400, detail=f"Message exceeds {char_limit} character limit")

    analysis = (
        await db.execute(select(SkinAnalysis).where(SkinAnalysis.id == analysis_id))
    ).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if analysis.status != "completed":
        raise HTTPException(status_code=409, detail="Analysis not completed")

    # Message limit
    used = (
        await db.execute(
            select(func.count())
            .select_from(SkinChatMessage)
            .where(
                SkinChatMessage.skin_analysis_id == analysis_id,
                SkinChatMessage.user_id == user.id,
                SkinChatMessage.role == "user",
            )
        )
    ).scalar_one()

    max_messages = 999_999 if is_paid else settings.CHAT_MSG_LIMIT_FREE
    if int(used) >= max_messages:
        raise HTTPException(
            status_code=429,
            detail="Message limit reached. Top up to unlock unlimited messages.",
        )

    # Billing
    await cm.deduct_for_skin_chat(user=user, skin_analysis_id=analysis_id)

    # Build context from analysis result
    result = analysis.analysis_result or {}
    context_lines = ["SKIN ANALYSIS CONTEXT:"]
    context_lines.append(f"Severity: {result.get('severity', 'unknown')}")

    conditions = result.get("conditions") or []
    if conditions:
        context_lines.append("\nCONDITIONS:")
        for c in conditions:
            context_lines.append(
                f"- {c.get('name', 'Unknown')} ({c.get('confidence', '')} confidence): {c.get('description', '')}"
            )

    recommendations = result.get("recommendations") or []
    if recommendations:
        context_lines.append("\nRECOMMENDATIONS:")
        for r in recommendations:
            context_lines.append(f"- {r}")

    context = "\n".join(context_lines)

    # Chat history
    history = (
        await db.execute(
            select(SkinChatMessage)
            .where(SkinChatMessage.skin_analysis_id == analysis_id, SkinChatMessage.user_id == user.id)
            .order_by(SkinChatMessage.created_at.asc())
        )
    ).scalars().all()

    llm_messages = [{"role": h.role, "content": h.content} for h in history]
    llm_messages.append({"role": "user", "content": msg})

    provider = KimiProvider()
    assistant_text = await provider.chat(messages=llm_messages, scan_context=context, mode="skin")

    # Store messages
    user_row = SkinChatMessage(skin_analysis_id=analysis_id, user_id=user.id, role="user", content=msg)
    assistant_row = SkinChatMessage(skin_analysis_id=analysis_id, user_id=user.id, role="assistant", content=assistant_text)
    db.add_all([user_row, assistant_row])
    await db.commit()

    tariffs = await cm._get_tariffs()
    remaining = max_messages - (int(used) + 1)
    return ChatSendResponse(
        message=assistant_text,
        remaining_messages=remaining,
        cost_kobo=tariffs.cost_per_chat_kobo,
        balance_kobo=user.credits,
    )
