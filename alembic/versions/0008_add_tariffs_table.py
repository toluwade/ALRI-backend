"""add tariffs table for admin-configurable pricing

Revision ID: 0008_tariffs
Revises: 0007_admin_promo
Create Date: 2026-03-08

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_tariffs"
down_revision = "0007_admin_promo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer(), primary_key=True, default=1),
        sa.Column("signup_bonus_kobo", sa.Integer(), nullable=False, server_default="500000"),
        sa.Column("referral_bonus_kobo", sa.Integer(), nullable=False, server_default="100000"),
        sa.Column("cost_per_chat_kobo", sa.Integer(), nullable=False, server_default="5000"),
        sa.Column("cost_per_file_upload_kobo", sa.Integer(), nullable=False, server_default="5000"),
        sa.Column("cost_per_transcription_kobo", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("cost_per_scan_unlock_kobo", sa.Integer(), nullable=False, server_default="20000"),
        sa.Column("cost_per_skin_analysis_kobo", sa.Integer(), nullable=False, server_default="25000"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Seed the single settings row with defaults
    op.execute(
        "INSERT INTO tariffs (id) VALUES (1)"
    )


def downgrade() -> None:
    op.drop_table("tariffs")
