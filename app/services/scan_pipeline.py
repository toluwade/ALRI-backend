from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

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


# Lines that are clearly not markers (headers, metadata, patient info)
_SKIP_LINE = re.compile(
    r"(?:"
    r"patient\s*name|doctor|hospital|laboratory|specimen|investigation|"
    r"collection\s*date|reported\s*date|test\s+param|test\s+report|"
    r"reference\s+range|medical\s+lab|scientist|"
    r"\bsex\s*:|\bage\s*:|\bname\s*:|\bnumber\s*:|\bdate\s*:|"
    r"^\s*results?\s*$|^\s*unit\s*$|www\.|\.com|@"
    r")",
    re.IGNORECASE,
)


def _try_parse_line(line: str) -> dict | None:
    """Try multiple regex patterns to extract a marker from a single line."""

    # Pattern 1: Table with reference range
    # e.g. "AST/GOT  35.5  0 - 46  u/l"  or  "TOTAL CHOLESTEROL  4.0  ≤5.20  mmol/l"
    m = re.match(
        r"^([A-Za-z][A-Za-z0-9\s\-\(\)\/\.]*?)"  # 1: marker name (lazy)
        r"\s+"
        r"(\d+(?:\.\d+)?)"  # 2: result value
        r"\s+"
        r"("  # 3: reference range
        r"[<>≤≥]?\s*\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?"  # "0 - 46"
        r"|[<>≤≥]\s*\d+(?:\.\d+)?"  # "≤5.20"
        r")"
        r"\s+"
        r"([A-Za-z%][A-Za-z0-9%\/]*(?:\/[A-Za-z]+)?)"  # 4: unit
        r"\s*$",
        line,
    )
    if m:
        return {
            "name": m.group(1).strip(),
            "value": _safe_float(m.group(2)),
            "unit": m.group(4).strip(),
            "ocr_reference": m.group(3).strip(),
        }

    # Pattern 2: Simple table — NAME  VALUE  [UNIT] (no reference range)
    m = re.match(
        r"^([A-Za-z][A-Za-z0-9\s\-\(\)\/]+?)"
        r"\s+"
        r"(\d+(?:\.\d+)?)"
        r"\s*"
        r"([A-Za-z%\/][A-Za-z0-9%\/]*)?\s*$",
        line,
    )
    if m:
        return {
            "name": m.group(1).strip(),
            "value": _safe_float(m.group(2)),
            "unit": (m.group(3) or "").strip() or None,
        }

    # Pattern 3: Colon-separated — "pH: 5.0" or "Specific gravity: 1.030"
    m = re.match(
        r"^([A-Za-z][A-Za-z0-9\s\-\(\)\/]*?)"
        r"\s*:\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*"
        r"([A-Za-z%\/][A-Za-z0-9%\/]*)?\s*$",
        line,
    )
    if m:
        return {
            "name": m.group(1).strip(),
            "value": _safe_float(m.group(2)),
            "unit": (m.group(3) or "").strip() or None,
        }

    return None


def parse_markers_from_text(text: str) -> list[dict]:
    """Robust parser for OCR text from lab reports.

    Handles:
    - Table format: NAME  VALUE  REF_LOW - REF_HIGH  UNIT
    - Simple format: NAME  VALUE  UNIT
    - Colon format:  NAME: VALUE  UNIT  (urinalysis etc.)
    """
    markers: list[dict] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or len(line) < 3:
            continue
        if _SKIP_LINE.search(line):
            continue

        result = _try_parse_line(line)
        if result and result.get("value") is not None:
            markers.append(result)

    # De-dupe by name keeping first
    seen: set[str] = set()
    out: list[dict] = []
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
        ref_low = ref_high = None

        # Prefer reference range extracted from the OCR text (the lab's own ranges)
        ocr_ref = m.get("ocr_reference")
        if ocr_ref:
            range_m = re.match(r"[<>≤≥]?\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)", ocr_ref)
            if range_m:
                ref_low = _safe_float(range_m.group(1))
                ref_high = _safe_float(range_m.group(2))
            else:
                bound_m = re.match(r"([<>≤≥])\s*(\d+(?:\.\d+)?)", ocr_ref)
                if bound_m:
                    val = _safe_float(bound_m.group(2))
                    if bound_m.group(1) in ("<", "≤"):
                        ref_low, ref_high = 0.0, val
                    elif bound_m.group(1) in (">", "≥"):
                        ref_low, ref_high = val, None

        # Fall back to built-in reference ranges
        builtin_low, builtin_high, default_unit = get_reference_range(m.get("name") or "", profile)
        if ref_low is None and ref_high is None:
            ref_low, ref_high = builtin_low, builtin_high

        unit = m.get("unit") or default_unit
        ref_range = None
        if ref_low is not None and ref_high is not None:
            ref_range = f"{ref_low}-{ref_high}"
        enriched.append(
            {
                "name": m.get("name"),
                "value": m.get("value"),
                "unit": unit,
                "reference_low": ref_low,
                "reference_high": ref_high,
                "reference_range": ref_range,
            }
        )
    return enriched


def _pdf_to_page_pngs(pdf_bytes: bytes, max_pages: int = 5) -> list[bytes]:
    """Convert PDF pages to PNG bytes list. Extracted once, reused for OCR + vision."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "input.pdf"
        pdf_path.write_bytes(pdf_bytes)
        subprocess.run(
            ["pdftoppm", "-png", "-r", "300", str(pdf_path), str(Path(tmpdir) / "page")],
            check=True, capture_output=True, timeout=60,
        )
        pages = sorted(Path(tmpdir).glob("page-*.png"))
        return [p.read_bytes() for p in pages[:max_pages]]


async def run_upload_pipeline(*, db: AsyncSession, scan_id: uuid.UUID, file_path: str, mime_type: str) -> None:
    scan = await db.get(Scan, scan_id)
    if not scan:
        return

    try:
        with open(file_path, "rb") as f:
            content = f.read()

        # Delete upload immediately — we only keep extracted data, not the report
        _delete_upload(file_path)
        scan.file_url = None

        is_pdf = "pdf" in (mime_type or "").lower()

        # For PDFs: convert pages to images ONCE (reused for both OCR and vision fallback)
        page_pngs: list[bytes] = []
        if is_pdf:
            try:
                page_pngs = _pdf_to_page_pngs(content)
            except Exception as e:
                logger.warning("PDF page extraction failed: %s", e)

        # OCR
        text = ""
        try:
            if page_pngs:
                # OCR the pre-extracted page images (no redundant PDF conversion)
                ocr = TesseractOCR()
                texts = []
                for png in page_pngs:
                    page_text = await ocr.extract_text(file_bytes=png, mime_type="image/png")
                    if page_text.strip():
                        texts.append(page_text.strip())
                text = "\n\n".join(texts)
            else:
                text = await TesseractOCR().extract_text(file_bytes=content, filename=file_path, mime_type=mime_type)
        except Exception as e:
            text = f"OCR_ERROR: {e}"

        scan.raw_ocr_text = text

        extracted = parse_markers_from_text(text)
        profile = await _get_profile(db, scan)
        llm = get_llm_provider()

        logger.info("OCR extracted %d markers from scan %s", len(extracted), scan.id)

        if len(extracted) < 2 and hasattr(llm, "interpret_image"):
            logger.info("Using VISION MODE for scan %s", scan.id)
            try:
                # Reuse pre-extracted first page for PDFs; raw bytes for images
                vision_bytes = page_pngs[0] if page_pngs else content
                vision_mime = "image/png" if page_pngs else mime_type

                interpreted = await llm.interpret_image(vision_bytes, vision_mime, profile)
                scan.raw_ocr_text = (text or "") + "\n\n[VISION MODE: OCR extracted <2 markers, sent image to LLM directly]"
            except Exception as vision_err:
                logger.error("Vision failed for scan %s: %s", scan.id, vision_err)
                enriched = _enrich_with_reference(extracted, profile)
                interpreted = await llm.interpret(enriched, profile)
                scan.raw_ocr_text = (text or "") + f"\n\n[VISION FAILED: {vision_err}, fell back to text]"
        else:
            enriched = _enrich_with_reference(extracted, profile)
            interpreted = await llm.interpret(enriched, profile)

        await _store_interpretation(db=db, scan=scan, interpreted=interpreted)
        scan.status = "completed"

        # Free memory — report content no longer needed
        del content
        del page_pngs
    except Exception as e:
        scan.status = "failed"
        scan.raw_ocr_text = (scan.raw_ocr_text or "") + f"\n\nPIPELINE_ERROR: {e}"
    finally:
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
