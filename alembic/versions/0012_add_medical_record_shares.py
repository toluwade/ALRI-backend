"""add medical_record_shares table

Revision ID: 0012_medrec_shares
Revises: 0011_multicurrency
Create Date: 2026-04-23

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_medrec_shares"
down_revision = "0011_multicurrency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "medical_record_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_medical_record_shares_user_id", "medical_record_shares", ["user_id"]
    )
    op.create_index(
        "ix_medical_record_shares_token",
        "medical_record_shares",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_medical_record_shares_token", table_name="medical_record_shares")
    op.drop_index("ix_medical_record_shares_user_id", table_name="medical_record_shares")
    op.drop_table("medical_record_shares")
