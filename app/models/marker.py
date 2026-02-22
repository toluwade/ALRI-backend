from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Marker(Base):
    __tablename__ = "markers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), index=True)

    name: Mapped[str | None] = mapped_column(String(100), index=True)
    value: Mapped[float | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(String(20))

    reference_low: Mapped[float | None] = mapped_column(Numeric)
    reference_high: Mapped[float | None] = mapped_column(Numeric)

    status: Mapped[str | None] = mapped_column(String(20))
    explanation: Mapped[str | None] = mapped_column(Text)

    is_preview: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scan = relationship("Scan", back_populates="markers")
