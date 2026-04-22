"""add user locale/currency prefs, topup packages, package prices, unified payments

Revision ID: 0011_multicurrency
Revises: 0010_support_tickets
Create Date: 2026-04-22

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_multicurrency"
down_revision = "0010_support_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User locale/currency prefs
    op.add_column("users", sa.Column("preferred_locale", sa.String(length=10), nullable=True))
    op.add_column("users", sa.Column("preferred_currency", sa.String(length=3), nullable=True))

    # TopUpPackage
    op.create_table(
        "topup_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_popular", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_topup_packages_code", "topup_packages", ["code"])

    # PackagePrice
    op.create_table(
        "package_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("topup_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("package_id", "currency", name="uq_package_currency"),
    )
    op.create_index("ix_package_prices_package_id", "package_prices", ["package_id"])
    op.create_index("ix_package_prices_currency", "package_prices", ["currency"])

    # Payment
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("topup_packages.id"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=200), nullable=False, unique=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("credits_granted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_provider", "payments", ["provider"])
    op.create_index("ix_payments_provider_reference", "payments", ["provider_reference"], unique=True)
    op.create_index("ix_payments_status", "payments", ["status"])

    # Seed default top-up packages (Starter / Pro / Power)
    op.execute(
        """
        INSERT INTO topup_packages (code, name, description, credits_granted, display_order, is_popular)
        VALUES
          ('starter', 'Starter', 'Good for occasional scans and chats', 500000, 1, false),
          ('pro',     'Pro',     'Best value \u2014 full dashboard access', 1500000, 2, true),
          ('power',   'Power',   'Power users with frequent analyses',   3500000, 3, false);
        """
    )
    # Seed market-specific prices (amount_minor in smallest unit per currency)
    op.execute(
        """
        WITH p AS (SELECT id, code FROM topup_packages)
        INSERT INTO package_prices (package_id, currency, amount_minor)
        SELECT p.id, c.currency, c.amount_minor
        FROM p
        JOIN (VALUES
          ('starter', 'NGN', 500000),    -- \u20a65,000
          ('starter', 'USD', 400),        -- $4.00
          ('starter', 'EUR', 380),        -- \u20ac3.80
          ('starter', 'GBP', 320),        -- \u00a33.20
          ('starter', 'USDT', 400),       -- 4.00 USDT
          ('pro',     'NGN', 1500000),    -- \u20a615,000
          ('pro',     'USD', 1200),       -- $12.00
          ('pro',     'EUR', 1150),       -- \u20ac11.50
          ('pro',     'GBP', 950),        -- \u00a39.50
          ('pro',     'USDT', 1200),      -- 12.00 USDT
          ('power',   'NGN', 3500000),    -- \u20a635,000
          ('power',   'USD', 2800),       -- $28.00
          ('power',   'EUR', 2650),       -- \u20ac26.50
          ('power',   'GBP', 2200),       -- \u00a322.00
          ('power',   'USDT', 2800)       -- 28.00 USDT
        ) AS c(code, currency, amount_minor)
          ON c.code = p.code;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_provider_reference", table_name="payments")
    op.drop_index("ix_payments_provider", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("ix_package_prices_currency", table_name="package_prices")
    op.drop_index("ix_package_prices_package_id", table_name="package_prices")
    op.drop_table("package_prices")

    op.drop_index("ix_topup_packages_code", table_name="topup_packages")
    op.drop_table("topup_packages")

    op.drop_column("users", "preferred_currency")
    op.drop_column("users", "preferred_locale")
