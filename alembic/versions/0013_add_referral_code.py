"""add users.referral_code and backfill

Revision ID: 0013_referral_code
Revises: 0012_medrec_shares
Create Date: 2026-04-23

"""
from __future__ import annotations

import random
import string

from alembic import op
import sqlalchemy as sa

revision = "0013_referral_code"
down_revision = "0012_medrec_shares"
branch_labels = None
depends_on = None


CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LEN = 6


def _gen_code() -> str:
    # Ambiguous characters (0/O, 1/I) included — volume is small enough that
    # collisions are cheap to retry. If it becomes a problem we can switch to
    # a clearer alphabet in a later migration.
    return "".join(random.choices(CODE_ALPHABET, k=CODE_LEN))


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("referral_code", sa.String(length=12), nullable=True)
    )
    op.create_index(
        "ix_users_referral_code", "users", ["referral_code"], unique=True
    )

    # Backfill existing users with unique codes.
    conn = op.get_bind()
    user_ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM users")).fetchall()]
    used: set[str] = set()
    for uid in user_ids:
        for _ in range(10):
            code = _gen_code()
            if code in used:
                continue
            try:
                conn.execute(
                    sa.text("UPDATE users SET referral_code = :c WHERE id = :id"),
                    {"c": code, "id": uid},
                )
                used.add(code)
                break
            except sa.exc.IntegrityError:
                continue


def downgrade() -> None:
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_column("users", "referral_code")
