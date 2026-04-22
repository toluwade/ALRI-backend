"""Payment provider abstraction.

Each provider implements the PaymentProvider protocol: create an invoice,
verify a webhook, and verify a payment by reference.

The Payment model records the unified state; CreditTransaction remains
the source-of-truth ledger.
"""
from app.services.payments.base import (
    PaymentProvider,
    PaymentInitResult,
    PaymentStatus,
    PaymentVerification,
    UnsupportedCurrencyError,
)
from app.services.payments.registry import get_provider, available_providers

__all__ = [
    "PaymentProvider",
    "PaymentInitResult",
    "PaymentStatus",
    "PaymentVerification",
    "UnsupportedCurrencyError",
    "get_provider",
    "available_providers",
]
