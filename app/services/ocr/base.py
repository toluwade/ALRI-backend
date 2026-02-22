from __future__ import annotations

from typing import Protocol


class BaseOCRProvider(Protocol):
    async def extract_text(self, file_bytes: bytes, filename: str) -> str:
        raise NotImplementedError
