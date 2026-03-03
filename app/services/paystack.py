"""Paystack payment integration.

Supports card, bank transfer, Opay, USSD — all via Paystack's unified API.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PAYSTACK_API = "https://api.paystack.co"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}


async def initialize_transaction(
    email: str,
    amount_kobo: int,
    reference: str,
    metadata: dict | None = None,
    callback_url: str | None = None,
) -> dict:
    """Initialize a Paystack transaction.

    Args:
        email: Customer email
        amount_kobo: Amount in kobo (NGN * 100)
        reference: Unique transaction reference
        metadata: Extra data (user_id, credits, etc.)
        callback_url: Redirect URL after payment
    """
    payload: dict = {
        "email": email,
        "amount": amount_kobo,
        "reference": reference,
        "currency": "NGN",
        "channels": ["card", "bank", "ussd", "bank_transfer", "opay"],
    }
    if metadata:
        payload["metadata"] = metadata
    if callback_url:
        payload["callback_url"] = callback_url

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYSTACK_API}/transaction/initialize",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"]


async def verify_transaction(reference: str) -> dict:
    """Verify a Paystack transaction by reference."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PAYSTACK_API}/transaction/verify/{reference}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"]
