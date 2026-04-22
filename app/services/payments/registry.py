"""Provider registry — returns the right provider for a given code/currency."""
from __future__ import annotations

from app.services.payments.base import PaymentProvider, UnsupportedCurrencyError


def get_provider(code: str) -> PaymentProvider:
    """Look up a provider by code ('paystack' | 'stripe' | 'nowpayments')."""
    # Lazy imports to avoid pulling provider SDKs unless they're used
    if code == "paystack":
        from app.services.payments.paystack_provider import PaystackProvider
        return PaystackProvider()
    if code == "stripe":
        from app.services.payments.stripe_provider import StripeProvider
        return StripeProvider()
    if code == "nowpayments":
        from app.services.payments.nowpayments_provider import NOWPaymentsProvider
        return NOWPaymentsProvider()
    raise ValueError(f"Unknown payment provider: {code}")


def available_providers() -> list[str]:
    """Providers currently configured with credentials."""
    from app.config import settings

    providers = []
    if settings.PAYSTACK_SECRET_KEY:
        providers.append("paystack")
    if settings.STRIPE_SECRET_KEY:
        providers.append("stripe")
    if settings.NOWPAYMENTS_API_KEY:
        providers.append("nowpayments")
    return providers


def provider_for_currency(currency: str) -> PaymentProvider:
    """Pick the best provider for a given currency."""
    if currency == "NGN":
        return get_provider("paystack")
    if currency in {"USD", "EUR", "GBP"}:
        return get_provider("stripe")
    if currency == "USDT":
        return get_provider("nowpayments")
    raise UnsupportedCurrencyError(f"No provider for currency {currency}")
