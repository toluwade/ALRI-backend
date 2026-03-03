"""widen credit_transactions reason column from 50 to 150

Revision ID: 0005_widen_reason
Revises: 0004_add_notifications
Create Date: 2026-03-02

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_widen_reason"
down_revision = "0004_add_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "credit_transactions",
        "reason",
        existing_type=sa.String(50),
        type_=sa.String(150),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "credit_transactions",
        "reason",
        existing_type=sa.String(150),
        type_=sa.String(50),
        existing_nullable=False,
    )
