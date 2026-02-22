from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Interpretation(Base):
    __tablename__ = "interpretations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), unique=True, index=True)

    summary: Mapped[str | None] = mapped_column(Text)
    correlations: Mapped[dict | list | None] = mapped_column(JSONB)
    report_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scan = relationship("Scan", back_populates="interpretation")
