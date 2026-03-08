"""add skin_chat_messages table

Revision ID: 0009_skin_chat
Revises: 0008_tariffs
Create Date: 2026-03-08

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_skin_chat"
down_revision = "0008_tariffs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skin_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "skin_analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skin_analyses.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("skin_chat_messages")
