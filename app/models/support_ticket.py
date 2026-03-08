from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )

    # account | billing | scans | skin_analysis | technical | other
    category: Mapped[str] = mapped_column(String(30))

    # complaint | feedback | bug_report | feature_request | testimonial
    type: Mapped[str] = mapped_column(String(30), default="feedback")

    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)

    # open | in_progress | resolved | closed
    status: Mapped[str] = mapped_column(String(20), default="open")

    # low | normal | high | urgent
    priority: Mapped[str] = mapped_column(String(10), default="normal")

    # Admin response
    admin_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    responded_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # User satisfaction rating (1-5) after resolution
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
