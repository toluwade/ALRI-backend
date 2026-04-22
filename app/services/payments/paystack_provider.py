"""Paystack provider implementation."""
from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

from app.config import settings
from app.services.payments.base import (
    PaymentInitResult,
    PaymentStatus,
    PaymentVerification,
    UnsupportedCurrencyError,
)

logger = logging.getLogger(__name__)

PAYSTACK_API = "https://api.paystack.co"


class PaystackProvider:
    code = "paystack"
    supported_currencies = ("NGN",)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

    async def create_invoice(
        self,
        *,
        reference: str,
        user_email: str | None,
        amount_minor: int,
        currency: str,
        metadata: dict,
        return_url: str | None = None,
    ) -> PaymentInitResult:
        if currency != "NGN":
            raise UnsupportedCurrencyError(f"Paystack only supports NGN, got {currency}")
        if not user_email:
            raise ValueError("Paystack requires user_email")

        payload: dict = {
            "email": user_email,
            "amount": amount_minor,  # kobo
            "reference": reference,
            "currency": "NGN",
            "channels": ["card", "bank", "ussd", "bank_transfer", "opay"],
            "metadata": metadata,
        }
        if return_url:
            payload["callback_url"] = return_url

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PAYSTACK_API}/transaction/initialize",
                headers=self._headers(),
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()["data"]

        return PaymentInitResult(
            reference=data["reference"],
            checkout_url=data["authorization_url"],
            extra={"access_code": data.get("access_code")},
        )

    async def verify(self, *, reference: str) -> PaymentVerification:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{PAYSTACK_API}/transaction/verify/{reference}",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()["data"]

        status_map = {
            "success": PaymentStatus.SUCCEEDED,
            "failed": PaymentStatus.FAILED,
            "abandoned": PaymentStatus.FAILED,
            "reversed": PaymentStatus.REFUNDED,
        }
        return PaymentVerification(
            status=status_map.get(data["status"], PaymentStatus.PENDING),
            currency=data.get("currency", "NGN"),
            amount_minor=int(data["amount"]),
            extra={"channel": data.get("channel"), "gateway_response": data.get("gateway_response")},
        )

    def verify_webhook_signature(self, *, payload: bytes, headers: dict) -> bool:
        secret = settings.PAYSTACK_WEBHOOK_SECRET or settings.PAYSTACK_SECRET_KEY
        if not secret:
            return False
        received = headers.get("x-paystack-signature") or headers.get("X-Paystack-Signature")
        if not received:
            return False
        expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, received)
