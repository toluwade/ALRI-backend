from __future__ import annotations

import base64

import httpx

from app.config import settings


class GoogleVisionOCR:
    async def extract_text(self, *, content: bytes, mime_type: str) -> str:
        if not settings.GOOGLE_VISION_API_KEY:
            raise RuntimeError("GOOGLE_VISION_API_KEY not configured")

        b64 = base64.b64encode(content).decode("utf-8")
        url = f"https://vision.googleapis.com/v1/images:annotate?key={settings.GOOGLE_VISION_API_KEY}"
        payload = {
            "requests": [
                {
                    "image": {"content": b64},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                }
            ]
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        try:
            return data["responses"][0]["fullTextAnnotation"]["text"]
        except Exception:
            return ""
