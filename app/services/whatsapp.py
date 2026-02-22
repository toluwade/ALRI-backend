from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Minimal Meta WhatsApp Cloud API client."""

    GRAPH_BASE = "https://graph.facebook.com/v19.0"

    def __init__(self):
        if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
            logger.warning("WhatsApp settings missing; client calls will fail")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}", "Content-Type": "application/json"}

    async def send_text(self, *, to: str, body: str) -> None:
        url = f"{self.GRAPH_BASE}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                logger.error("WhatsApp send failed: %s %s", resp.status_code, resp.text)
                resp.raise_for_status()

    async def get_media_url(self, *, media_id: str) -> str:
        url = f"{self.GRAPH_BASE}/{media_id}"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"})
            resp.raise_for_status()
            data = resp.json()
            return data["url"]

    async def download_media(self, *, media_url: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(media_url, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"})
            resp.raise_for_status()
            return resp.content


def extract_inbound_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extracts message objects from Meta webhook payload."""

    msgs: list[dict[str, Any]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            for m in value.get("messages", []) or []:
                msgs.append(m)
    return msgs
