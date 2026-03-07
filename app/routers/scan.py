from __future__ import annotations

import logging
import mimetypes
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.rate_limit import rate_limit
from app.models import Interpretation, Marker, Scan, User
from app.schemas.scan import ManualScanRequest, PreviewResponse, StatusCounts, StatusResponse, UploadResponse
from app.schemas.marker import MarkerOut
from app.tasks.scan_tasks import process_upload, process_manual
from app.utils.storage import save_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scan", tags=["scan"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_MIMES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
    "image/webp",
}

# Magic bytes for reliable file-type detection (mobile browsers send wrong MIME)
_MAGIC = {
    b"%PDF": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
}


def _detect_mime(content: bytes, declared_mime: str, filename: str) -> str:
    """Determine real MIME type from magic bytes, falling back to declared/guessed."""
    for magic, mime in _MAGIC.items():
        if content[:len(magic)] == magic:
            return mime
    # HEIC/HEIF: ftyp box at offset 4
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"hevc"):
            return "image/heic"
    # Fall back to declared or guessed
    mime = declared_mime or mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
    return mime


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
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    mime = _detect_mime(content, file.content_type or "", file.filename or "")
    if mime not in ALLOWED_MIMES:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload a PDF, JPG, PNG, or HEIC.")

    path = save_upload(filename=file.filename or "upload", content=content)

    scan = Scan(status="processing", input_type="upload", file_url=path, source=source, user_id=(current_user.id if current_user else None))
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    # Dispatch to Celery (falls back to sync execution if Redis unavailable)
    try:
        process_upload.delay(str(scan.id), path, mime)
    except Exception as e:
        scan.status = "failed"
        scan.raw_ocr_text = f"PIPELINE_ERROR: {e}"
        await db.commit()
    return UploadResponse(scan_id=str(scan.id), status=scan.status or "processing")


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
    try:
        process_manual.delay(str(scan.id), manual_markers)
    except Exception as e:
        scan.status = "failed"
        scan.raw_ocr_text = f"PIPELINE_ERROR: {e}"
        await db.commit()
    return UploadResponse(scan_id=str(scan.id), status=scan.status or "processing")


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

    # Fetch interpretation for summary
    interp = (
        await db.execute(select(Interpretation).where(Interpretation.scan_id == scan.id))
    ).scalar_one_or_none()

    preview_summary = interp.summary if interp else None

    # Count marker statuses
    counts = StatusCounts()
    for m in markers:
        status = (m.status or "").lower()
        if status == "normal":
            counts.normal += 1
        elif status == "borderline_high":
            counts.borderline_high += 1
        elif status == "borderline_low":
            counts.borderline_low += 1
        elif status == "high":
            counts.high += 1
        elif status == "low":
            counts.low += 1
        elif status == "critical":
            counts.critical += 1

    created_at = scan.created_at.isoformat() if scan.created_at else None

    return PreviewResponse(
        scan_status=scan.status or "processing",
        locked=not scan.full_unlocked,
        preview_markers=preview,
        total_markers=len(markers),
        preview_summary=preview_summary,
        status_counts=counts,
        created_at=created_at,
    )
