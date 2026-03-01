from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.models.skin_analysis import SkinAnalysis
from app.services.credit_manager import CreditManager
from app.services.skin_analyzer import SkinAnalyzer
from app.utils.storage import save_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skin", tags=["skin"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


class SkinAnalysisResponse(BaseModel):
    id: str
    status: str
    analysis: dict | None
    cost_kobo: int
    balance_kobo: int


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


@router.get("/{analysis_id}", response_model=SkinAnalysisResponse)
async def get_skin_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a past skin analysis."""
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
