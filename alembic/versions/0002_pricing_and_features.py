"""add user tier, skin_analyses, voice_transcriptions

Revision ID: 0002_pricing_and_features
Revises: 0001_init
Create Date: 2026-02-28

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0002_pricing_and_features"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- users: add has_topped_up --
    op.add_column(
        "users",
        sa.Column("has_topped_up", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # Backfill: mark users who already paid via Paystack as paid
    op.execute(
        "UPDATE users SET has_topped_up = true "
        "WHERE id IN ("
        "  SELECT DISTINCT user_id FROM credit_transactions "
        "  WHERE reason LIKE 'paystack_success:%'"
        ")"
    )

    # -- skin_analyses --
    op.create_table(
        "skin_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("analysis_result", postgresql.JSON(), nullable=True),
        sa.Column("credit_deducted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'processing'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_skin_analyses_user_id", "skin_analyses", ["user_id"])

    # -- voice_transcriptions --
    op.create_table(
        "voice_transcriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id"), nullable=True),
        sa.Column("audio_url", sa.Text(), nullable=True),
        sa.Column("transcription", sa.Text(), nullable=True),
        sa.Column("credit_deducted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_voice_transcriptions_user_id", "voice_transcriptions", ["user_id"])
    op.create_index("ix_voice_transcriptions_scan_id", "voice_transcriptions", ["scan_id"])


def downgrade() -> None:
    op.drop_table("voice_transcriptions")
    op.drop_table("skin_analyses")
    op.drop_column("users", "has_topped_up")
