from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing|completed|failed
    input_type: Mapped[str | None] = mapped_column(String(10))  # upload|manual

    file_url: Mapped[str | None] = mapped_column(Text)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(20))  # web|mobile|whatsapp

    preview_unlocked: Mapped[bool] = mapped_column(Boolean, default=True)
    full_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_deducted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="scans", lazy="selectin")
    markers = relationship("Marker", back_populates="scan", cascade="all, delete-orphan", lazy="selectin")
    interpretation = relationship("Interpretation", back_populates="scan", uselist=False, cascade="all, delete-orphan", lazy="selectin")
