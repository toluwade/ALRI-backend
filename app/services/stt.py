from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SpeechToText:
    """OpenAI Whisper speech-to-text service."""

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio to text using OpenAI Whisper API.

        Returns transcribed text string.
        """
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured for speech-to-text")

        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}

        files = {"file": (filename, audio_bytes)}
        data = {"model": "whisper-1"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()

        text = result.get("text", "").strip()
        logger.info("Whisper transcribed %d bytes → %d chars", len(audio_bytes), len(text))
        return text
