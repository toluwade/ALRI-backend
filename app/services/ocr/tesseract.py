from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
import pytesseract


class TesseractOCR:
    async def extract_text(self, file_bytes: bytes = None, filename: str = "", *, content: bytes = None, mime_type: str = "") -> str:
        # Support both call signatures
        data = file_bytes or content or b""
        mt = mime_type or ""
        fname = filename or ""

        # Determine type from mime or filename
        is_pdf = "pdf" in mt.lower() or fname.lower().endswith(".pdf")
        is_image = any(x in mt.lower() for x in ["image", "png", "jpeg", "jpg", "webp", "heic"]) or \
                   any(fname.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".heic"])

        if is_pdf:
            return self._extract_pdf(data)
        elif is_image or data:
            return self._extract_image(data)
        else:
            # Try as image anyway
            return self._extract_image(data)

    def _extract_image(self, content: bytes) -> str:
        img = Image.open(io.BytesIO(content))
        return pytesseract.image_to_string(img)

    def _extract_pdf(self, content: bytes) -> str:
        """Convert PDF pages to images then OCR each page."""
        texts = []
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "input.pdf"
            pdf_path.write_bytes(content)

            # Try pdftoppm (poppler) first
            try:
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "300", str(pdf_path), str(Path(tmpdir) / "page")],
                    check=True, capture_output=True, timeout=60,
                )
                for img_path in sorted(Path(tmpdir).glob("page-*.png")):
                    img = Image.open(img_path)
                    text = pytesseract.image_to_string(img)
                    if text.strip():
                        texts.append(text.strip())
            except (subprocess.CalledProcessError, FileNotFoundError):
                # pdftoppm not available — try PIL direct (won't work for most PDFs)
                try:
                    img = Image.open(io.BytesIO(content))
                    texts.append(pytesseract.image_to_string(img))
                except Exception:
                    raise RuntimeError("PDF OCR requires poppler-utils (pdftoppm). Install with: apt-get install poppler-utils")

        return "\n\n".join(texts)
