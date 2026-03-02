from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )

    type: Mapped[str] = mapped_column(String(30))
    # Types: scan_completed, credit_received, credit_deducted,
    #        new_referral, newsletter, login_session,
    #        support_ticket, system_update

    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    ref_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
