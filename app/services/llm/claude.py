from __future__ import annotations

from app.services.llm.kimi import KimiProvider


class ClaudeProvider(KimiProvider):
    """Placeholder for future Claude integration.

    For now, this behaves like KimiProvider to keep the interface stable.
    """

    MODEL = "claude-haiku-4-5-20251001"
