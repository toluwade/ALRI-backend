from __future__ import annotations

import json
import logging
import os
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.reference_ranges import get_reference_range
from app.models import Interpretation, Marker, Scan, User
from app.services.llm.factory import get_llm_provider
from app.services.ocr.tesseract import TesseractOCR
from app.services.preview_selector import select_preview_markers

logger = logging.getLogger(__name__)


def _delete_upload(file_path: str) -> None:
    """Remove the uploaded file from disk after extraction. Best-effort, never raises."""
    try:
        if file_path and os.path.isfile(file_path):
            os.remove(file_path)
            logger.info("Deleted upload: %s", file_path)
    except OSError as e:
        logger.warning("Could not delete upload %s: %s", file_path, e)


MEDICAL_DISCLAIMER = (
    "This interpretation is for informational purposes only and is not medical advice. "
    "Always consult a qualified healthcare professional about your results."
)


def _safe_float(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None


def parse_markers_from_text(text: str) -> list[dict]:
    """Very lightweight parser for OCR text.

    Real lab PDFs vary widely; this is a best-effort baseline.
    We look for lines like: "Glucose 92 mg/dL".
    """
    markers: list[dict] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or len(line) < 4:
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9\s\-\(\)\/]+?)\s+([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z%\/]+)?\s*$", line)
        if not m:
            continue
        name = m.group(1).strip()
        value = _safe_float(m.group(2))
        unit = (m.group(3) or "").strip() or None
        if value is None:
            continue
        markers.append({"name": name, "value": value, "unit": unit})

    # De-dupe by name keeping first
    seen = set()
    out = []
    for mk in markers:
        key = mk["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(mk)
    return out


async def _get_profile(db: AsyncSession, scan: Scan) -> dict | None:
    if not scan.user_id:
        return None
    res = await db.execute(select(User).where(User.id == scan.user_id))
    user = res.scalar_one_or_none()
    if not user:
        return None
    return {"age": user.age, "sex": user.sex}


def _enrich_with_reference(markers: list[dict], profile: dict | None) -> list[dict]:
    enriched = []
    for m in markers:
        low, high, default_unit = get_reference_range(m.get("name") or "", profile)
        unit = m.get("unit") or default_unit
        ref_range = None
        if low is not None and high is not None:
            ref_range = f"{low}-{high}"
        enriched.append(
            {
                "name": m.get("name"),
                "value": m.get("value"),
                "unit": unit,
                "reference_low": low,
                "reference_high": high,
                "reference_range": ref_range,
            }
        )
    return enriched


async def run_upload_pipeline(*, db: AsyncSession, scan_id: uuid.UUID, file_path: str, mime_type: str) -> None:
    scan = await db.get(Scan, scan_id)
    if not scan:
        return

    try:
        with open(file_path, "rb") as f:
            content = f.read()

        # OCR: Tesseract with preprocessing (PaddleOCR requires x86, this server is ARM64)
        text = ""
        try:
            text = await TesseractOCR().extract_text(file_bytes=content, filename=file_path, mime_type=mime_type)
        except Exception as e:
            text = f"OCR_ERROR: {e}"

        scan.raw_ocr_text = text

        extracted = parse_markers_from_text(text)
        profile = await _get_profile(db, scan)
        llm = get_llm_provider()

        # If OCR extracted few/no markers, send image directly to LLM (vision)
        logger.info("OCR extracted %d markers from scan %s", len(extracted), scan.id)

        if len(extracted) < 2 and hasattr(llm, "interpret_image"):
            logger.info("Using VISION MODE for scan %s", scan.id)
            try:
                interpreted = await llm.interpret_image(content, mime_type, profile)
                scan.raw_ocr_text = (text or "") + "\n\n[VISION MODE: OCR extracted <2 markers, sent image to LLM directly]"
            except Exception as vision_err:
                logger.error("Vision failed for scan %s: %s", scan.id, vision_err)
                # Fall back to text-based interpretation
                enriched = _enrich_with_reference(extracted, profile)
                interpreted = await llm.interpret(enriched, profile)
                scan.raw_ocr_text = (text or "") + f"\n\n[VISION FAILED: {vision_err}, fell back to text]"
        else:
            enriched = _enrich_with_reference(extracted, profile)
            interpreted = await llm.interpret(enriched, profile)
        await _store_interpretation(db=db, scan=scan, interpreted=interpreted)

        scan.status = "completed"
    except Exception as e:
        scan.status = "failed"
        scan.raw_ocr_text = (scan.raw_ocr_text or "") + f"\n\nPIPELINE_ERROR: {e}"
    finally:
        # Clean up: delete the uploaded file — extracted data is in the DB now
        _delete_upload(file_path)
        scan.file_url = None
        await db.commit()


async def run_manual_pipeline(*, db: AsyncSession, scan_id: uuid.UUID, manual_markers: list[dict]) -> None:
    scan = await db.get(Scan, scan_id)
    if not scan:
        return

    try:
        profile = await _get_profile(db, scan)
        enriched = _enrich_with_reference(manual_markers, profile)

        llm = get_llm_provider()
        interpreted = await llm.interpret(enriched, profile)
        await _store_interpretation(db=db, scan=scan, interpreted=interpreted)
        scan.status = "completed"
    except Exception as e:
        scan.status = "failed"
        scan.raw_ocr_text = (scan.raw_ocr_text or "") + f"\n\nPIPELINE_ERROR: {e}"
    finally:
        await db.commit()


async def _store_interpretation(*, db: AsyncSession, scan: Scan, interpreted: dict) -> None:
    # Clear existing markers (idempotency)
    for m in list(scan.markers or []):
        await db.delete(m)

    markers = interpreted.get("markers") or []

    # Preview selection
    selected = select_preview_markers(markers, max_items=4)
    selected_names = {str(m.get("name")) for m in selected}

    for m in markers:
        # reference_range might be like "13.5-17.5"
        ref_low = ref_high = None
        ref = m.get("reference_range")
        if isinstance(ref, str) and "-" in ref:
            parts = ref.split("-", 1)
            ref_low = _safe_float(parts[0])
            ref_high = _safe_float(parts[1])

        mk = Marker(
            scan_id=scan.id,
            name=m.get("name"),
            value=_safe_float(m.get("value")),
            unit=m.get("unit"),
            reference_low=ref_low,
            reference_high=ref_high,
            status=m.get("status"),
            explanation=m.get("explanation"),
            is_preview=str(m.get("name")) in selected_names,
        )
        db.add(mk)

    interp = Interpretation(
        scan_id=scan.id,
        summary=(interpreted.get("summary") or "") + f"\n\n{MEDICAL_DISCLAIMER}",
        correlations=interpreted.get("correlations") or [],
        report_url=interpreted.get("report_url"),
    )
    db.add(interp)

    # Store preview into scan raw text as debug (optional)
    scan.preview_unlocked = True
    scan.full_unlocked = False

    # Ensure JSON serializable
    json.dumps(interpreted, default=str)
