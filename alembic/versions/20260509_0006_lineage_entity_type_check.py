"""add CHECK constraint for lineage entity types

Revision ID: 20260509_0006
Revises: 20260509_0005
Create Date: 2026-05-09 17:30:00
"""

from __future__ import annotations

from alembic import op


revision = "20260509_0006"
down_revision = "20260509_0005"
branch_labels = None
depends_on = None


_ALLOWED = (
    "source",
    "dataset",
    "schema_version",
    "dataset_version",
    "feature_set",
    "experiment",
    "model",
)
_LIST = ", ".join(f"'{t}'" for t in _ALLOWED)


def upgrade() -> None:
    op.create_check_constraint(
        "ck_lineage_from_entity_type",
        "lineage_edges",
        f"from_entity_type IN ({_LIST})",
    )
    op.create_check_constraint(
        "ck_lineage_to_entity_type",
        "lineage_edges",
        f"to_entity_type IN ({_LIST})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_lineage_to_entity_type", "lineage_edges", type_="check")
    op.drop_constraint("ck_lineage_from_entity_type", "lineage_edges", type_="check")
