"""add weight_kg and height_cm to users

Revision ID: 0003_add_weight_height
Revises: 0002_pricing_and_features
Create Date: 2026-03-02

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_add_weight_height"
down_revision = "0002_pricing_and_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("weight_kg", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("height_cm", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "height_cm")
    op.drop_column("users", "weight_kg")
