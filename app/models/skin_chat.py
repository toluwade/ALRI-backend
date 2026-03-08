from __future__ import annotations

import uuid

from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SkinChatMessage(Base):
    __tablename__ = "skin_chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    skin_analysis_id = mapped_column(UUID(as_uuid=True), ForeignKey("skin_analyses.id"), index=True)
    user_id = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    role = mapped_column(String(10))  # "user" | "assistant"
    content = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
