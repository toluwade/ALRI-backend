from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import Interpretation, Marker, Scan, User
from app.services.credit_manager import CreditManager
from app.services.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


MEDICAL_DISCLAIMER = (
    "AI-generated interpretation for informational purposes only; not medical advice. "
    "Always consult a qualified healthcare professional."
)

router = APIRouter(prefix="/scan", tags=["scan"])


class FullScanResponse(BaseModel):
    markers: list[dict]
    summary: str | None
    correlations: list[dict] | None
    report_url: str | None
    disclaimer: str


@router.get("/{scan_id}/full", response_model=FullScanResponse)
async def get_scan_full(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FullScanResponse:
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    # Claim unclaimed scan (anonymous scan created before signup)
    if scan.user_id is None:
        logger.info("Claiming scan %s for user %s", scan_id, user.id)
        scan.user_id = user.id
        await db.commit()
        await db.refresh(scan)
    elif scan.user_id != user.id:
        logger.warning(
            "Scan %s belongs to user %s, but user %s requested it",
            scan_id, scan.user_id, user.id,
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    # Must be completed
    if scan.status != "completed":
        raise HTTPException(status_code=409, detail=f"Scan not completed (status={scan.status})")

    cm = CreditManager(db)
    await cm.require_and_deduct_for_full_scan(user=user, scan=scan)

    markers = (
        await db.execute(select(Marker).where(Marker.scan_id == scan_id).order_by(Marker.created_at.asc()))
    ).scalars().all()
    interpretation = (
        await db.execute(select(Interpretation).where(Interpretation.scan_id == scan_id))
    ).scalar_one_or_none()

    marker_dicts: list[dict] = []
    for m in markers:
        marker_dicts.append(
            {
                "name": m.name,
                "value": float(m.value) if m.value is not None else None,
                "unit": m.unit,
                "reference_low": float(m.reference_low) if m.reference_low is not None else None,
                "reference_high": float(m.reference_high) if m.reference_high is not None else None,
                "status": m.status,
                "explanation": m.explanation,
            }
        )

    correlations = None
    report_url = None
    summary = None
    if interpretation:
        summary = interpretation.summary
        correlations = interpretation.correlations if isinstance(interpretation.correlations, list) else None
        report_url = interpretation.report_url

    return FullScanResponse(
        markers=marker_dicts,
        summary=summary,
        correlations=correlations,
        report_url=report_url or f"/api/v1/scan/{scan_id}/report",
        disclaimer=MEDICAL_DISCLAIMER,
    )


class SharedScanResponse(BaseModel):
    markers: list[dict]
    summary: str | None
    correlations: list[dict] | None
    total_markers: int
    abnormal_count: int
    shared_by: str | None
    disclaimer: str


@router.get("/{scan_id}/shared", response_model=SharedScanResponse)
async def get_scan_shared(
    scan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SharedScanResponse:
    """Public endpoint — returns full results for completed + unlocked scans."""
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan.status != "completed":
        raise HTTPException(status_code=409, detail="Scan not yet completed")

    if not scan.full_unlocked:
        raise HTTPException(status_code=403, detail="Scan results have not been unlocked")

    markers = (
        await db.execute(select(Marker).where(Marker.scan_id == scan_id).order_by(Marker.created_at.asc()))
    ).scalars().all()
    interpretation = (
        await db.execute(select(Interpretation).where(Interpretation.scan_id == scan_id))
    ).scalar_one_or_none()

    marker_dicts: list[dict] = []
    abnormal = 0
    for m in markers:
        if m.status and m.status != "normal":
            abnormal += 1
        marker_dicts.append(
            {
                "name": m.name,
                "value": float(m.value) if m.value is not None else None,
                "unit": m.unit,
                "reference_low": float(m.reference_low) if m.reference_low is not None else None,
                "reference_high": float(m.reference_high) if m.reference_high is not None else None,
                "status": m.status,
                "explanation": m.explanation,
            }
        )

    summary = None
    correlations = None
    if interpretation:
        summary = interpretation.summary
        correlations = interpretation.correlations if isinstance(interpretation.correlations, list) else None

    # Resolve the scan owner's name (relationship is selectin-loaded)
    shared_by = scan.user.name if scan.user else None

    return SharedScanResponse(
        markers=marker_dicts,
        summary=summary,
        correlations=correlations,
        total_markers=len(marker_dicts),
        abnormal_count=abnormal,
        shared_by=shared_by,
        disclaimer=MEDICAL_DISCLAIMER,
    )


@router.get("/{scan_id}/report")
async def get_scan_report(
    scan_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalar_one_or_none()
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.user_id is None:
        scan.user_id = user.id
        await db.commit()
        await db.refresh(scan)
    elif scan.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if scan.status != "completed":
        raise HTTPException(status_code=409, detail=f"Scan not completed (status={scan.status})")

    markers = (
        await db.execute(select(Marker).where(Marker.scan_id == scan_id).order_by(Marker.created_at.asc()))
    ).scalars().all()
    interpretation = (
        await db.execute(select(Interpretation).where(Interpretation.scan_id == scan_id))
    ).scalar_one_or_none()

    marker_dicts = [
        {
            "name": m.name,
            "value": float(m.value) if m.value is not None else None,
            "unit": m.unit,
            "status": m.status,
            "reference_range": f"{m.reference_low}-{m.reference_high}" if m.reference_low is not None else None,
        }
        for m in markers
    ]

    user_profile = {"age": user.age, "sex": user.sex} if user.age or user.sex else None

    gen = ReportGenerator()
    pdf_bytes = gen.generate_pdf(
        scan_id=scan_id,
        markers=marker_dicts,
        summary=interpretation.summary if interpretation else None,
        correlations=interpretation.correlations if interpretation and isinstance(interpretation.correlations, list) else None,
        user_profile=user_profile,
        user_name=user.name,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="alri-report-{scan_id}.pdf"'},
    )
