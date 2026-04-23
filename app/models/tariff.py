"""Platform tariffs — single-row table for admin-configurable pricing."""
from __future__ import annotations

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # All amounts in kobo (₦1 = 100 kobo)
    signup_bonus_kobo: Mapped[int] = mapped_column(Integer, default=500_000)          # ₦5,000
    referral_bonus_kobo: Mapped[int] = mapped_column(Integer, default=50_000)         # ₦500
    cost_per_chat_kobo: Mapped[int] = mapped_column(Integer, default=5_000)           # ₦50
    cost_per_file_upload_kobo: Mapped[int] = mapped_column(Integer, default=5_000)    # ₦50
    cost_per_transcription_kobo: Mapped[int] = mapped_column(Integer, default=10_000) # ₦100
    cost_per_scan_unlock_kobo: Mapped[int] = mapped_column(Integer, default=20_000)   # ₦200
    cost_per_skin_analysis_kobo: Mapped[int] = mapped_column(Integer, default=25_000) # ₦250

    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
