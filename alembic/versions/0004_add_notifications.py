"""add notifications table

Revision ID: 0004_add_notifications
Revises: 0003_add_weight_height
Create Date: 2026-03-02

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "0004_add_notifications"
down_revision = "0003_add_weight_height"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("ref_id", sa.String(50), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_notifications_user_id", "notifications", ["user_id"]
    )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_created")
    op.drop_index("ix_notifications_user_id")
    op.drop_table("notifications")
