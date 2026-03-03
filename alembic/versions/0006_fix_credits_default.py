"""fix credits server_default from 5 to 0

The initial migration (0001) had server_default='5' (typo — should have been
500000).  Now that signup bonus is granted explicitly via CreditManager.grant(),
the correct server_default is 0.

Revision ID: 0006_fix_credits_default
Revises: 0005_widen_reason
Create Date: 2026-03-03

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_fix_credits_default"
down_revision = "0005_widen_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        existing_type=sa.Integer(),
        server_default=sa.text("0"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "credits",
        existing_type=sa.Integer(),
        server_default=sa.text("5"),
        existing_nullable=False,
    )
