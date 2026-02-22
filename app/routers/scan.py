from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.rate_limit import rate_limit
from app.models import Interpretation, Marker, Scan, User
from app.schemas.scan import ManualScanRequest, PreviewResponse, StatusResponse, UploadResponse
from app.schemas.marker import MarkerOut
from app.tasks.scan_tasks import process_manual, process_upload
from app.utils.storage import save_upload

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("/upload", response_model=UploadResponse, dependencies=[Depends(rate_limit)])
async def upload_scan(
    request: Request,
    file: UploadFile = File(...),
    source: str | None = None,
    current_user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")

    path = save_upload(filename=file.filename or "upload", content=content)
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"

    scan = Scan(status="processing", input_type="upload", file_url=path, source=source, user_id=(current_user.id if current_user else None))
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    process_upload.delay(str(scan.id), path, mime)
    return UploadResponse(scan_id=str(scan.id), status="processing")


@router.post("/manual", response_model=UploadResponse, dependencies=[Depends(rate_limit)])
async def manual_scan(
    payload: ManualScanRequest,
    source: str | None = None,
    current_user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    scan = Scan(status="processing", input_type="manual", source=source, user_id=(current_user.id if current_user else None))
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    manual_markers = [{"name": m.marker, "value": m.value, "unit": m.unit} for m in payload.markers]
    process_manual.delay(str(scan.id), manual_markers)

    return UploadResponse(scan_id=str(scan.id), status="processing")


@router.get("/{scan_id}/status", response_model=StatusResponse, dependencies=[Depends(rate_limit)])
async def scan_status(scan_id: str, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    scan = await db.get(Scan, uuid.UUID(scan_id))
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return StatusResponse(status=scan.status)


@router.get("/{scan_id}/preview", response_model=PreviewResponse, dependencies=[Depends(rate_limit)])
async def scan_preview(scan_id: str, db: AsyncSession = Depends(get_db)) -> PreviewResponse:
    scan = await db.get(Scan, uuid.UUID(scan_id))
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    res = await db.execute(select(Marker).where(Marker.scan_id == scan.id).order_by(Marker.created_at.asc()))
    markers = res.scalars().all()

    preview = [
        MarkerOut(
            name=m.name,
            value=float(m.value) if m.value is not None else None,
            unit=m.unit,
            reference_low=float(m.reference_low) if m.reference_low is not None else None,
            reference_high=float(m.reference_high) if m.reference_high is not None else None,
            status=m.status,
            explanation=m.explanation,
            is_preview=m.is_preview,
        )
        for m in markers
        if m.is_preview
    ]

    return PreviewResponse(preview_markers=preview, total_markers=len(markers))
