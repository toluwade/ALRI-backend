from __future__ import annotations

import json
import re

import httpx

from app.config import settings
from app.data.reference_ranges import REFERENCE_RANGES


SYSTEM_PROMPT = """You are ALRI, an Automated Lab Result Interpreter. Your job is to analyze
lab test results and explain them in plain, simple language that anyone
can understand.

For each biomarker provided:
1. Compare the value against standard reference ranges
2. Classify as: normal, borderline_high, borderline_low, high, low, or critical
3. Write a one-sentence explanation a non-medical person would understand
4. Flag any values that need urgent attention

After analyzing all markers:
5. Write a 2-3 sentence overall health summary in plain language
6. Identify any cross-marker correlations (e.g., low iron + low hemoglobin = possible iron deficiency)

IMPORTANT:
- Use simple, reassuring language. Avoid medical jargon.
- Never diagnose conditions. Use phrases like "may suggest" or "could indicate"
- Always recommend consulting a healthcare provider
- If age/sex is provided, adjust reference ranges accordingly

Respond ONLY in this JSON format:
{
  "markers": [
    {
      "name": "Hemoglobin",
      "value": 13.5,
      "unit": "g/dL",
      "reference_range": "13.5-17.5",
      "status": "normal",
      "explanation": "Your hemoglobin is within the healthy range, meaning your blood is carrying oxygen well."
    }
  ],
  "summary": "Overall, your results look good...",
  "correlations": [
    {
      "markers": ["Iron", "Hemoglobin"],
      "finding": "Both your iron and hemoglobin are low, which together may suggest iron deficiency. Consider discussing this with your doctor."
    }
  ]
}
"""


def _extract_json(text: str) -> dict:
    # LLMs sometimes wrap JSON in fences; be defensive.
    m = re.search(r"\{[\s\S]*\}\s*$", text.strip())
    if not m:
        raise ValueError("LLM did not return JSON")
    return json.loads(m.group(0))


class KimiProvider:
    """Kimi K2 via NVIDIA NIM — OpenAI-compatible API."""

    BASE_URL = "https://integrate.api.nvidia.com/v1"
    MODEL = "moonshotai/kimi-k2-instruct"

    async def interpret(self, markers: list[dict], profile: dict | None) -> dict:
        base_url = settings.NVIDIA_NIM_BASE_URL or self.BASE_URL
        model = settings.KIMI_MODEL or self.MODEL
        if not settings.NVIDIA_NIM_API_KEY:
            # Offline/dev fallback: return a minimal structure so pipeline can complete.
            return {
                "markers": [
                    {
                        "name": m.get("name"),
                        "value": m.get("value"),
                        "unit": m.get("unit"),
                        "reference_range": m.get("reference_range"),
                        "status": "normal",
                        "explanation": "Result received. Please consult a healthcare provider for interpretation.",
                    }
                    for m in markers
                ],
                "summary": "Results received. This is not medical advice. Consider discussing your results with a healthcare provider.",
                "correlations": [],
            }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "profile": profile,
                            "reference_ranges_hint": REFERENCE_RANGES,
                            "markers": markers,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.2,
        }

        headers = {"Authorization": f"Bearer {settings.NVIDIA_NIM_API_KEY}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        return _extract_json(content)
