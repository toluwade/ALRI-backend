from __future__ import annotations

import io

from PIL import Image
import pytesseract


class TesseractOCR:
    async def extract_text(self, *, content: bytes, mime_type: str) -> str:
        # Simple image-only fallback.
        if mime_type in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
            img = Image.open(io.BytesIO(content))
            return pytesseract.image_to_string(img)
        # PDF handling would require pdf->image conversion (poppler). Keep minimal for now.
        raise RuntimeError(f"Tesseract fallback does not support mime type: {mime_type}")
