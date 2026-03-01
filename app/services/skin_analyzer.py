from __future__ import annotations

import base64
import json
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VISION_MODEL = "nvidia/llama-3.1-nemotron-nano-vl-8b-v1"

SKIN_SYSTEM_PROMPT = """\
You are a medical image analysis assistant specialising in dermatology.
Analyse the uploaded skin image and provide a preliminary assessment.

Return ONLY valid JSON in this exact structure:
{
  "conditions": [
    {"name": "...", "confidence": "high|moderate|low", "description": "..."}
  ],
  "recommendations": ["...", "..."],
  "severity": "mild|moderate|severe|unknown",
  "disclaimer": "This is an AI-assisted preliminary assessment and NOT a medical diagnosis. Always consult a qualified dermatologist or healthcare professional for proper diagnosis and treatment."
}

Guidelines:
- List 1-3 most likely conditions with confidence level.
- Always include "Consult a dermatologist" in recommendations.
- Be descriptive but concise.
- If the image is unclear or not a skin condition, say so.
"""


class SkinAnalyzer:
    """AI-powered skin condition analysis using NVIDIA vision model."""

    async def analyze(self, image_bytes: bytes, mime_type: str) -> dict:
        if not settings.NVIDIA_NIM_API_KEY:
            raise ValueError("NVIDIA NIM API key not configured")

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        payload = {
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SKIN_SYSTEM_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
        }

        headers = {"Authorization": f"Bearer {settings.NVIDIA_NIM_API_KEY}"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.NVIDIA_NIM_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]

        m = re.search(r"\{[\s\S]*\}", content.strip())
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                logger.warning("Failed to parse skin analysis JSON: %s", content[:200])

        return {
            "conditions": [],
            "recommendations": ["Could not analyse image. Please try again or consult a dermatologist."],
            "severity": "unknown",
            "disclaimer": "This is an AI-assisted preliminary assessment and NOT a medical diagnosis.",
        }
