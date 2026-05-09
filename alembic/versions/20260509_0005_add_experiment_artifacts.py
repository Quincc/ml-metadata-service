"""add notebook_url and report_path to experiments

Revision ID: 20260509_0005
Revises: 20260509_0004
Create Date: 2026-05-09 16:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260509_0005"
down_revision = "20260509_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("experiments")}
    if "notebook_url" not in existing:
        op.add_column("experiments", sa.Column("notebook_url", sa.String(length=512), nullable=True))
    if "report_path" not in existing:
        op.add_column("experiments", sa.Column("report_path", sa.String(length=512), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("experiments")}
    if "report_path" in existing:
        op.drop_column("experiments", "report_path")
    if "notebook_url" in existing:
        op.drop_column("experiments", "notebook_url")
