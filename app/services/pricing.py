"""Pricing service — market-specific package prices per currency."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import PackagePrice, TopUpPackage

# Minimum supported currencies. Keep aligned with frontend routing + messages.
SUPPORTED_CURRENCIES = ("NGN", "USD", "EUR", "GBP", "USDT")

# Country -> preferred currency map (CF-IPCountry header)
COUNTRY_TO_CURRENCY = {
    "NG": "NGN",
    "US": "USD",
    "GB": "GBP",
    "UK": "GBP",
    "FR": "EUR",
    "DE": "EUR",
    "NL": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "BE": "EUR",
    "AT": "EUR",
    "IE": "EUR",
    "PT": "EUR",
    "FI": "EUR",
}


def currency_for_country(country_code: str | None) -> str:
    """Map ISO-2 country code to our preferred currency. Falls back to USD."""
    if not country_code:
        return "USD"
    return COUNTRY_TO_CURRENCY.get(country_code.upper(), "USD")


async def list_packages_for_currency(
    db: AsyncSession,
    currency: str,
) -> list[dict]:
    """Return active packages with prices in the given currency."""
    currency = currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        currency = "USD"

    result = await db.execute(
        select(TopUpPackage, PackagePrice)
        .join(PackagePrice, PackagePrice.package_id == TopUpPackage.id)
        .where(
            TopUpPackage.is_active.is_(True),
            PackagePrice.currency == currency,
            PackagePrice.is_active.is_(True),
        )
        .order_by(TopUpPackage.display_order.asc(), TopUpPackage.id.asc())
    )
    rows = result.all()
    return [
        {
            "id": pkg.id,
            "code": pkg.code,
            "name": pkg.name,
            "description": pkg.description,
            "credits_granted": pkg.credits_granted,
            "is_popular": pkg.is_popular,
            "currency": price.currency,
            "amount_minor": price.amount_minor,
        }
        for pkg, price in rows
    ]


async def get_package_price(
    db: AsyncSession,
    package_code: str,
    currency: str,
) -> dict | None:
    """Return a single package + price, or None."""
    currency = currency.upper()
    result = await db.execute(
        select(TopUpPackage, PackagePrice)
        .join(PackagePrice, PackagePrice.package_id == TopUpPackage.id)
        .where(
            TopUpPackage.code == package_code,
            TopUpPackage.is_active.is_(True),
            PackagePrice.currency == currency,
            PackagePrice.is_active.is_(True),
        )
        .limit(1)
    )
    row = result.first()
    if not row:
        return None
    pkg, price = row
    return {
        "id": pkg.id,
        "code": pkg.code,
        "name": pkg.name,
        "credits_granted": pkg.credits_granted,
        "currency": price.currency,
        "amount_minor": price.amount_minor,
    }
