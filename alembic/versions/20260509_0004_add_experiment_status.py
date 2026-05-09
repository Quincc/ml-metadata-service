"""add status column to experiments

Revision ID: 20260509_0004
Revises: 20260509_0003
Create Date: 2026-05-09 15:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260509_0004"
down_revision = "20260509_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="finished",
        ),
    )


def downgrade() -> None:
    op.drop_column("experiments", "status")
