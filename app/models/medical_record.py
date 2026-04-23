"""Medical record share tokens — signed, revocable read-only links."""
from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MedicalRecordShare(Base):
    __tablename__ = "medical_record_shares"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    viewed_count: Mapped[int] = mapped_column(Integer, default=0)

    # Optional message shown at the top of the shared view, e.g.
    # "For my GP, Dr. Okonkwo — recent lipid results".
    note: Mapped[str | None] = mapped_column(Text)

    # Reserved for future per-category opt-outs.
    scopes: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
