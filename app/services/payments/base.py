"""Shared types for payment providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class UnsupportedCurrencyError(ValueError):
    """Raised when a provider cannot process the requested currency."""


@dataclass
class PaymentInitResult:
    """Returned by provider.create_invoice — what the frontend needs to redirect the user."""

    reference: str
    checkout_url: str | None = None  # hosted checkout URL (Paystack/Stripe/NOWPayments)
    extra: dict = field(default_factory=dict)  # e.g., payment_address for crypto


@dataclass
class PaymentVerification:
    """Returned by provider.verify — canonical state + amounts the provider saw."""

    status: PaymentStatus
    currency: str
    amount_minor: int
    extra: dict = field(default_factory=dict)


class PaymentProvider(Protocol):
    """Protocol all payment providers implement."""

    code: str  # 'paystack' | 'stripe' | 'nowpayments'
    supported_currencies: tuple[str, ...]

    async def create_invoice(
        self,
        *,
        reference: str,
        user_email: str | None,
        amount_minor: int,
        currency: str,
        metadata: dict,
        return_url: str | None = None,
    ) -> PaymentInitResult: ...

    async def verify(self, *, reference: str) -> PaymentVerification: ...

    def verify_webhook_signature(self, *, payload: bytes, headers: dict) -> bool: ...
