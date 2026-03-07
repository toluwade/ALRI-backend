"""add is_admin to users, create promo_codes and promo_redemptions tables

Revision ID: 0007_admin_promo
Revises: 0006_fix_credits_default
Create Date: 2026-03-07

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0007_admin_promo"
down_revision = "0006_fix_credits_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_admin column to users
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Create promo_codes table
    op.create_table(
        "promo_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("discount_kobo", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_uses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create promo_redemptions table
    op.create_table(
        "promo_redemptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("promo_code_id", UUID(as_uuid=True), sa.ForeignKey("promo_codes.id"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("credited_kobo", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("promo_redemptions")
    op.drop_table("promo_codes")
    op.drop_column("users", "is_admin")
