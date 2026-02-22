"""initial schema

Revision ID: 0001_init
Revises: 
Create Date: 2026-02-22

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=255), unique=True, nullable=True),
        sa.Column("phone", sa.String(length=20), unique=True, nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("auth_provider", sa.String(length=20), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(length=10), nullable=True),
        sa.Column("credits", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("referred_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_phone", "users", ["phone"], unique=False)

    op.create_table(
        "scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'processing'"), nullable=False),
        sa.Column("input_type", sa.String(length=10), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("raw_ocr_text", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("preview_unlocked", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("full_unlocked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("credit_deducted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "markers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("reference_low", sa.Numeric(), nullable=True),
        sa.Column("reference_high", sa.Numeric(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("is_preview", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_markers_scan_id", "markers", ["scan_id"], unique=False)
    op.create_index("ix_markers_name", "markers", ["name"], unique=False)

    op.create_table(
        "interpretations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("correlations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("report_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("scan_id", name="uq_interpretations_scan_id"),
    )
    op.create_index("ix_interpretations_scan_id", "interpretations", ["scan_id"], unique=True)

    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"], unique=False)
    op.create_index("ix_credit_transactions_scan_id", "credit_transactions", ["scan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_credit_transactions_scan_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")

    op.drop_index("ix_interpretations_scan_id", table_name="interpretations")
    op.drop_table("interpretations")

    op.drop_index("ix_markers_name", table_name="markers")
    op.drop_index("ix_markers_scan_id", table_name="markers")
    op.drop_table("markers")

    op.drop_table("scans")

    op.drop_index("ix_users_phone", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
