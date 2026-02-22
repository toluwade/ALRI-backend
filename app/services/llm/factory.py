from __future__ import annotations

from app.config import settings
from app.services.llm.base import BaseLLMProvider
from app.services.llm.claude import ClaudeProvider
from app.services.llm.kimi import KimiProvider


def get_llm_provider() -> BaseLLMProvider:
    provider = (settings.LLM_PROVIDER or "kimi").lower()
    if provider == "kimi":
        return KimiProvider()
    if provider == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unsupported LLM provider: {provider}")
