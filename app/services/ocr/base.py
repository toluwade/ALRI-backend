from __future__ import annotations

from typing import Protocol


class BaseOCRProvider(Protocol):
    async def extract_text(self, *, content: bytes, mime_type: str) -> str:
        raise NotImplementedError
