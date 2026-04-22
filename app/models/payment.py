"""Multi-currency top-up packages, prices, and unified payment records.

Supports Paystack (NGN), Stripe (USD/EUR/GBP/NGN), and NOWPayments (USDT ERC20/TRC20).
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TopUpPackage(Base):
    """A top-up bundle users can purchase (e.g., "starter", "pro", "power").

    Prices are market-specific via PackagePrice rows.
    """

    __tablename__ = "topup_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # starter | pro | power | custom
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    credits_granted: Mapped[int] = mapped_column(Integer)  # kobo-equivalent credits
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    prices = relationship("PackagePrice", back_populates="package", cascade="all, delete-orphan", lazy="selectin")


class PackagePrice(Base):
    """Price for a package in a specific currency (smallest unit, e.g., cents/kobo)."""

    __tablename__ = "package_prices"
    __table_args__ = (UniqueConstraint("package_id", "currency", name="uq_package_currency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("topup_packages.id", ondelete="CASCADE"), index=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)  # NGN | USD | EUR | GBP | USDT
    amount_minor: Mapped[int] = mapped_column(Integer)  # price in smallest unit
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    package = relationship("TopUpPackage", back_populates="prices", lazy="selectin")


class Payment(Base):
    """Unified payment record across providers (Paystack, Stripe, NOWPayments)."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    package_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("topup_packages.id"))

    provider: Mapped[str] = mapped_column(String(30), index=True)  # paystack | stripe | nowpayments
    provider_reference: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    currency: Mapped[str] = mapped_column(String(10))
    amount_minor: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)  # pending | succeeded | failed | refunded
    credits_granted: Mapped[int] = mapped_column(Integer, default=0)

    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
