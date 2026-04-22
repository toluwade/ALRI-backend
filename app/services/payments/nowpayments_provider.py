"""NOWPayments provider (USDT ERC20 + TRC20, non-custodial mode).

Docs: https://documenter.getpostman.com/view/7907941/S1a32n38
"""
from __future__ import annotations

import hashlib
import hmac
import json
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


class NOWPaymentsProvider:
    code = "nowpayments"
    supported_currencies = ("USDT",)  # we accept either usdterc20 or usdttrc20 at invoice time

    def _headers(self) -> dict:
        return {"x-api-key": settings.NOWPAYMENTS_API_KEY or ""}

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
        if currency != "USDT":
            raise UnsupportedCurrencyError(f"NOWPayments only supports USDT here, got {currency}")

        # NOWPayments uses decimal price, not cents
        price_amount = amount_minor / 100.0
        # Default to TRC20 (cheap gas); caller can override via metadata["pay_currency"]
        pay_currency = metadata.get("pay_currency", "usdttrc20")
        if pay_currency not in {"usdterc20", "usdttrc20"}:
            raise ValueError(f"Unsupported USDT network: {pay_currency}")

        payload = {
            "price_amount": price_amount,
            "price_currency": "usd",  # base price in USD
            "pay_currency": pay_currency,
            "order_id": reference,
            "order_description": metadata.get("package_name", "ALRI top-up"),
            "ipn_callback_url": f"{settings.APP_URL}/webhook/nowpayments",
            "success_url": return_url or f"{settings.FRONTEND_URL}/top-up?reference={reference}&status=success",
            "cancel_url": f"{settings.FRONTEND_URL}/top-up?reference={reference}&status=cancelled",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.NOWPAYMENTS_API_URL}/invoice",
                headers=self._headers(),
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

        return PaymentInitResult(
            reference=reference,
            checkout_url=data.get("invoice_url"),
            extra={
                "invoice_id": data.get("id"),
                "pay_currency": pay_currency,
                "pay_address": data.get("pay_address"),
            },
        )

    async def verify(self, *, reference: str) -> PaymentVerification:
        # Look up payment by order_id via list endpoint
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.NOWPAYMENTS_API_URL}/payment",
                headers=self._headers(),
                params={"order_id": reference, "limit": 1},
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()

        payments = body.get("data") or []
        if not payments:
            return PaymentVerification(status=PaymentStatus.PENDING, currency="USDT", amount_minor=0)

        p = payments[0]
        status_map = {
            "finished": PaymentStatus.SUCCEEDED,
            "confirmed": PaymentStatus.SUCCEEDED,
            "partially_paid": PaymentStatus.PENDING,
            "waiting": PaymentStatus.PENDING,
            "confirming": PaymentStatus.PENDING,
            "sending": PaymentStatus.PENDING,
            "failed": PaymentStatus.FAILED,
            "refunded": PaymentStatus.REFUNDED,
            "expired": PaymentStatus.FAILED,
        }
        return PaymentVerification(
            status=status_map.get(p.get("payment_status", ""), PaymentStatus.PENDING),
            currency="USDT",
            amount_minor=int(float(p.get("price_amount", 0)) * 100),
            extra={
                "payment_id": p.get("payment_id"),
                "pay_currency": p.get("pay_currency"),
                "actually_paid": p.get("actually_paid"),
            },
        )

    def verify_webhook_signature(self, *, payload: bytes, headers: dict) -> bool:
        secret = settings.NOWPAYMENTS_IPN_SECRET
        if not secret:
            return False
        received = headers.get("x-nowpayments-sig") or headers.get("X-Nowpayments-Sig")
        if not received:
            return False
        # NOWPayments signs the JSON body with HMAC-SHA512 using keys sorted alphabetically
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False
        normalized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(secret.encode(), normalized.encode(), hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, received)
