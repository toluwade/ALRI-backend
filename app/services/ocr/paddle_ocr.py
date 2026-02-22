"""PaddleOCR provider — PP-OCRv5 for text, PP-StructureV3 for table detection.

Runs entirely on CPU on the Hetzner box. No external API needed.
Models auto-download on first run.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from .base import BaseOCRProvider

logger = logging.getLogger(__name__)


class PaddleOCRProvider(BaseOCRProvider):
    """Extract text and tables from lab report images/PDFs using PaddleOCR."""

    def __init__(self) -> None:
        self._ocr = None
        self._table_engine = None

    def _get_ocr(self):
        """Lazy-init PP-OCRv5."""
        if self._ocr is None:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                ocr_version="PP-OCRv5",
                use_gpu=False,
                show_log=False,
            )
        return self._ocr

    def _get_table_engine(self):
        """Lazy-init PP-StructureV3 for table detection."""
        if self._table_engine is None:
            from paddleocr import PPStructure

            self._table_engine = PPStructure(
                recovery=True,
                use_gpu=False,
                show_log=False,
                structure_version="PP-StructureV3",
                lang="en",
            )
        return self._table_engine

    async def extract_text(self, file_bytes: bytes, filename: str) -> str:
        """Extract text from image or PDF using PaddleOCR.

        Flow:
        1. Try PP-StructureV3 for table-structured extraction (lab reports are tables)
        2. Fall back to PP-OCRv5 plain text extraction
        3. Combine results into structured text
        """
        import asyncio

        return await asyncio.get_event_loop().run_in_executor(
            None, self._extract_sync, file_bytes, filename
        )

    def _extract_sync(self, file_bytes: bytes, filename: str) -> str:
        suffix = Path(filename).suffix.lower() or ".png"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            # Try table structure extraction first (best for lab reports)
            lines = self._extract_tables(tmp_path)
            if lines:
                return "\n".join(lines)

            # Fall back to plain OCR
            return self._extract_plain(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _extract_tables(self, file_path: str) -> list[str]:
        """Use PP-StructureV3 to detect and extract tables."""
        try:
            engine = self._get_table_engine()
            results = engine(file_path)
            lines: list[str] = []

            for region in results:
                if region.get("type") == "table":
                    # Extract HTML table and convert to text rows
                    html = region.get("res", {}).get("html", "")
                    if html:
                        lines.extend(self._html_table_to_text(html))
                elif region.get("type") == "text":
                    text = region.get("res", {}).get("text", "")
                    if text.strip():
                        lines.append(text.strip())

            return lines
        except Exception as e:
            logger.warning("Table extraction failed, will use plain OCR: %s", e)
            return []

    def _extract_plain(self, file_path: str) -> str:
        """Plain PP-OCRv5 text extraction."""
        ocr = self._get_ocr()
        result = ocr.ocr(file_path, cls=True)

        lines: list[str] = []
        if result:
            for page in result:
                if page:
                    for line in page:
                        text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                        lines.append(text)

        return "\n".join(lines)

    @staticmethod
    def _html_table_to_text(html: str) -> list[str]:
        """Convert HTML table to tab-separated text lines."""
        try:
            from html.parser import HTMLParser

            class TableParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.rows: list[list[str]] = []
                    self.current_row: list[str] = []
                    self.current_cell = ""
                    self.in_cell = False

                def handle_starttag(self, tag, attrs):
                    if tag in ("td", "th"):
                        self.in_cell = True
                        self.current_cell = ""

                def handle_endtag(self, tag):
                    if tag in ("td", "th"):
                        self.in_cell = False
                        self.current_row.append(self.current_cell.strip())
                    elif tag == "tr":
                        if self.current_row:
                            self.rows.append(self.current_row)
                        self.current_row = []

                def handle_data(self, data):
                    if self.in_cell:
                        self.current_cell += data

            parser = TableParser()
            parser.feed(html)

            return ["\t".join(row) for row in parser.rows if any(row)]
        except Exception:
            return []
