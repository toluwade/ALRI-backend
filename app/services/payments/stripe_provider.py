"""Stripe provider implementation (Checkout Session + webhook)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

import httpx

from app.config import settings
from app.services.payments.base import (
    PaymentInitResult,
    PaymentStatus,
    PaymentVerification,
    UnsupportedCurrencyError,
)

logger = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com/v1"


class StripeProvider:
    code = "stripe"
    supported_currencies = ("USD", "EUR", "GBP", "NGN")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"}

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
        if currency not in self.supported_currencies:
            raise UnsupportedCurrencyError(f"Stripe does not support {currency}")

        success_url = return_url or f"{settings.FRONTEND_URL}/top-up?reference={reference}&status=success"
        cancel_url = f"{settings.FRONTEND_URL}/top-up?reference={reference}&status=cancelled"

        # Stripe uses form-encoded bodies; build nested line_items[...] keys
        form: dict[str, str] = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": reference,
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount_minor),
            "line_items[0][price_data][product_data][name]": metadata.get("package_name", "ALRI Top-up"),
            "line_items[0][quantity]": "1",
        }
        if user_email:
            form["customer_email"] = user_email
        for k, v in metadata.items():
            form[f"metadata[{k}]"] = str(v)
        form["metadata[reference]"] = reference

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{STRIPE_API}/checkout/sessions",
                headers=self._headers(),
                data=form,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        return PaymentInitResult(
            reference=reference,
            checkout_url=data["url"],
            extra={"session_id": data["id"]},
        )

    async def verify(self, *, reference: str) -> PaymentVerification:
        # Look up session by client_reference_id
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{STRIPE_API}/checkout/sessions",
                headers=self._headers(),
                params={"limit": 1},
                timeout=15,
            )
            # Fallback: we actually need to look up by client_reference_id.
            # Stripe doesn't support filtering directly, so the caller should
            # pass us the session_id in reference when possible. Accept either.
            resp.raise_for_status()

        if reference.startswith("cs_"):
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{STRIPE_API}/checkout/sessions/{reference}",
                    headers=self._headers(),
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            status_map = {
                "paid": PaymentStatus.SUCCEEDED,
                "unpaid": PaymentStatus.PENDING,
                "no_payment_required": PaymentStatus.SUCCEEDED,
            }
            return PaymentVerification(
                status=status_map.get(data.get("payment_status", "unpaid"), PaymentStatus.PENDING),
                currency=(data.get("currency") or "usd").upper(),
                amount_minor=int(data.get("amount_total", 0)),
                extra={"session_id": data["id"], "payment_intent": data.get("payment_intent")},
            )
        # If we only have client_reference_id, we can't easily verify without session_id.
        return PaymentVerification(
            status=PaymentStatus.PENDING,
            currency="USD",
            amount_minor=0,
            extra={"note": "verify requires stripe session_id"},
        )

    def verify_webhook_signature(self, *, payload: bytes, headers: dict) -> bool:
        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            return False
        sig_header = headers.get("stripe-signature") or headers.get("Stripe-Signature")
        if not sig_header:
            return False

        # Parse Stripe-Signature: "t=timestamp,v1=signature,..."
        items = dict(part.split("=", 1) for part in sig_header.split(",") if "=" in part)
        timestamp = items.get("t")
        signature = items.get("v1")
        if not timestamp or not signature:
            return False

        # Reject old timestamps (>5 min) to mitigate replay
        try:
            if abs(time.time() - int(timestamp)) > 300:
                return False
        except ValueError:
            return False

        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
