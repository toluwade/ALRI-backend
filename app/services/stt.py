from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0  # seconds

# Groq: free tier, very fast (LPU), 14,400 req/day
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"

# OpenAI: paid, slower, can hit rate limits easily
OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_MODEL = "whisper-1"


class SpeechToText:
    """Speech-to-text via Groq Whisper (preferred) or OpenAI Whisper (fallback)."""

    def _get_provider(self) -> tuple[str, str, str]:
        """Return (url, model, api_key) for the best available provider."""
        if settings.GROQ_API_KEY:
            return GROQ_URL, GROQ_MODEL, settings.GROQ_API_KEY
        if settings.OPENAI_API_KEY:
            return OPENAI_URL, OPENAI_MODEL, settings.OPENAI_API_KEY
        raise ValueError("No STT API key configured. Set GROQ_API_KEY (free) or OPENAI_API_KEY.")

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio to text.

        Retries up to MAX_RETRIES times on 429 rate-limit errors with exponential backoff.
        """
        url, model, api_key = self._get_provider()
        provider_name = "Groq" if "groq" in url else "OpenAI"
        headers = {"Authorization": f"Bearer {api_key}"}

        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES):
            files = {"file": (filename, audio_bytes)}
            data = {"model": model}

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)

            if resp.status_code == 429:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(
                    "%s Whisper 429 rate-limited, retrying in %.1fs (attempt %d/%d)",
                    provider_name, wait, attempt + 1, MAX_RETRIES,
                )
                last_exc = httpx.HTTPStatusError(
                    f"429 Too Many Requests (attempt {attempt + 1})",
                    request=resp.request,
                    response=resp,
                )
                await asyncio.sleep(wait)
                continue

            resp.raise_for_status()
            result = resp.json()
            text = result.get("text", "").strip()
            logger.info(
                "%s Whisper transcribed %d bytes → %d chars",
                provider_name, len(audio_bytes), len(text),
            )
            return text

        # All retries exhausted
        raise last_exc or RuntimeError(f"{provider_name} Whisper transcription failed after retries")
