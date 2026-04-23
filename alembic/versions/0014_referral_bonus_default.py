"""set referral_bonus_kobo default to 50,000 (₦500)

Revision ID: 0014_ref_bonus_default
Revises: 0013_referral_code
Create Date: 2026-04-23

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_ref_bonus_default"
down_revision = "0013_referral_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only update if the row is still at the previous default; don't overwrite
    # admin customisations.
    op.execute(
        "UPDATE tariffs SET referral_bonus_kobo = 50000 "
        "WHERE id = 1 AND referral_bonus_kobo = 100000"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE tariffs SET referral_bonus_kobo = 100000 "
        "WHERE id = 1 AND referral_bonus_kobo = 50000"
    )
