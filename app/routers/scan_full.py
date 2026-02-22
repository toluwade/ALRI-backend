from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import Interpretation, Marker, Scan, User
from app.services.credit_manager import CreditManager


MEDICAL_DISCLAIMER = (
    "AI-generated interpretation for informational purposes only; not medical advice. "
    "Always consult a qualified healthcare professional."
)

router = APIRouter(prefix="/api/v1/scan", tags=["scan"])


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

    # Auth required; scan must belong to user
    if scan.user_id != user.id:
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
