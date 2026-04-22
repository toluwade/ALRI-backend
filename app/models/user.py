from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(Text)

    auth_provider: Mapped[str | None] = mapped_column(String(20))  # google | apple | phone

    # Localization & currency preference (synced with Clerk publicMetadata)
    preferred_locale: Mapped[str | None] = mapped_column(String(10))  # en | fr | de | nl
    preferred_currency: Mapped[str | None] = mapped_column(String(10))  # NGN | USD | EUR | GBP | USDT

    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(10))  # male | female
    weight_kg: Mapped[float | None] = mapped_column(Integer)  # weight in kg
    height_cm: Mapped[float | None] = mapped_column(Integer)  # height in cm

    # Monetary balance stored in kobo (₦1 = 100 kobo)
    # Starts at 0; signup bonus is granted explicitly via CreditManager.grant()
    credits: Mapped[int] = mapped_column(Integer, default=0)

    # True once user has topped up real money via Paystack (distinguishes free vs paid)
    has_topped_up: Mapped[bool] = mapped_column(Boolean, default=False)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    referred_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    referrer = relationship("User", remote_side=[id], lazy="selectin")

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    scans = relationship("Scan", back_populates="user", lazy="selectin")
