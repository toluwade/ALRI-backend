from __future__ import annotations

import json
import re

import httpx

from app.config import settings
from app.data.reference_ranges import REFERENCE_RANGES


CHAT_SYSTEM_PROMPT = """You are ALRI's health assistant. The user is asking about their lab results.
You have their full report context below. Answer in plain, simple language.
- Never diagnose. Use "may suggest" or "could indicate"
- Always recommend consulting a healthcare provider for medical decisions
- Be helpful, reassuring, and clear
- Keep answers concise (2-4 sentences unless they ask for detail)
"""


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
    import logging
    logger = logging.getLogger(__name__)
    
    # Try to find JSON object in the response (may be wrapped in fences)
    cleaned = text.strip()
    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    
    # Try full object match
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}, text: {m.group(0)[:200]}")
    
    raise ValueError(f"LLM did not return JSON. Response: {text[:300]}")


class KimiProvider:
    """Kimi K2 via NVIDIA NIM — OpenAI-compatible API."""

    BASE_URL = "https://integrate.api.nvidia.com/v1"
    MODEL = "moonshotai/kimi-k2-instruct"

    async def interpret_image(self, image_bytes: bytes, mime_type: str, profile: dict | None) -> dict:
        """Two-step: vision model extracts markers from image → Kimi K2 interprets them."""
        import base64
        import logging

        logger = logging.getLogger(__name__)
        base_url = settings.NVIDIA_NIM_BASE_URL or self.BASE_URL
        vision_model = "nvidia/llama-3.1-nemotron-nano-vl-8b-v1"

        if not settings.NVIDIA_NIM_API_KEY:
            return {
                "markers": [],
                "summary": "Image received but no LLM API key configured.",
                "correlations": [],
            }

        # Step 1: Vision model extracts raw data from the image
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        extract_payload = {
            "model": vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract ALL lab test results from this medical lab report image. "
                                    "For each test, provide: test name, result value, unit, and reference range. "
                                    "Return as a JSON array like: "
                                    '[{"test": "Hemoglobin", "result": "14.5", "unit": "g/dL", "reference_range": "13.5-17.5"}]',
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        headers = {"Authorization": f"Bearer {settings.NVIDIA_NIM_API_KEY}"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=extract_payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        vision_text = data["choices"][0]["message"]["content"]
        logger.warning(f"Vision extracted: {vision_text[:300]}")

        # Parse the extracted markers
        try:
            # Try to find JSON array in the response
            arr_match = re.search(r"\[[\s\S]*\]", vision_text.strip())
            if arr_match:
                raw_markers = json.loads(arr_match.group(0))
            else:
                raw_markers = json.loads(vision_text)
        except json.JSONDecodeError:
            logger.error(f"Vision model didn't return valid JSON: {vision_text[:200]}")
            raw_markers = []

        if not raw_markers:
            return {
                "markers": [],
                "summary": "Could not extract lab results from this image. Try a clearer photo or enter values manually.",
                "correlations": [],
            }

        # Step 2: Convert to our marker format and send to Kimi K2 for interpretation
        markers_for_llm = []
        for m in raw_markers:
            name = m.get("test") or m.get("name") or ""
            value = m.get("result") or m.get("value") or ""
            unit = m.get("unit") or ""
            ref = m.get("reference_range") or ""

            try:
                val_float = float(str(value).replace(",", "").strip())
            except (ValueError, TypeError):
                val_float = None

            markers_for_llm.append({
                "name": name,
                "value": val_float if val_float is not None else value,
                "unit": unit,
                "reference_range": ref,
            })

        logger.warning(f"Sending {len(markers_for_llm)} markers to Kimi K2 for interpretation")
        return await self.interpret(markers_for_llm, profile)

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

    async def chat(self, *, messages: list[dict], scan_context: str) -> str:
        """Chat about a scan report.

        Args:
            messages: OpenAI-style messages (role/content), excluding system prompt.
            scan_context: Full report context to ground the assistant.
        """

        base_url = settings.NVIDIA_NIM_BASE_URL or self.BASE_URL
        model = settings.KIMI_MODEL or self.MODEL

        if not settings.NVIDIA_NIM_API_KEY:
            return (
                "I can help explain your results, but the AI service isn't configured right now. "
                "Please consult a healthcare provider for medical decisions."
            )

        # Prepend context as a user-visible instruction so the model always sees it.
        grounded_messages = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Report context:\n{scan_context}",
            },
        ]

        # Append conversation history (user/assistant turns)
        for m in messages:
            role = m.get("role")
            if role not in {"user", "assistant"}:
                continue
            grounded_messages.append({"role": role, "content": str(m.get("content") or "")})

        payload = {
            "model": model,
            "messages": grounded_messages,
            "temperature": 0.2,
        }

        headers = {"Authorization": f"Bearer {settings.NVIDIA_NIM_API_KEY}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return (data["choices"][0]["message"]["content"] or "").strip()
