"""add timestamps and soft delete columns

Revision ID: 20260416_0002
Revises: 20260416_0001
Create Date: 2026-04-16 21:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260416_0002"
down_revision = "20260416_0001"
branch_labels = None
depends_on = None


TABLES = [
    "data_sources",
    "datasets",
    "schema_versions",
    "dataset_versions",
    "feature_sets",
    "experiments",
    "lineage_edges",
]


def upgrade() -> None:
    for table_name in TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.drop_column(table_name, "deleted_at")
        op.drop_column(table_name, "updated_at")
