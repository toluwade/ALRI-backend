from __future__ import annotations

from typing import Protocol


class BaseLLMProvider(Protocol):
    async def interpret(self, markers: list[dict], profile: dict | None) -> dict:
        """Return dict with keys: markers, summary, correlations."""
        raise NotImplementedError
