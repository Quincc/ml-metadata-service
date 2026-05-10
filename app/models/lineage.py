from __future__ import annotations

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import TimeStampMixin

LINEAGE_ENTITY_TYPES = (
    "source",
    "dataset",
    "schema_version",
    "dataset_version",
    "feature_set",
    "experiment",
    "model",
)

_ENTITY_TYPE_LIST = ", ".join(f"'{t}'" for t in LINEAGE_ENTITY_TYPES)


class LineageEdge(TimeStampMixin, Base):
    """Связь происхождения данных между двумя сущностями."""

    __tablename__ = 'lineage_edges'
    __table_args__ = (
        CheckConstraint(
            f"from_entity_type IN ({_ENTITY_TYPE_LIST})",
            name="ck_lineage_from_entity_type",
        ),
        CheckConstraint(
            f"to_entity_type IN ({_ENTITY_TYPE_LIST})",
            name="ck_lineage_to_entity_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    from_entity_type: Mapped[str] = mapped_column(String(100), nullable=False, comment='Тип исходной сущности')
    from_entity_id: Mapped[int] = mapped_column(nullable=False, comment='ID исходной сущности')
    to_entity_type: Mapped[str] = mapped_column(String(100), nullable=False, comment='Тип целевой сущности')
    to_entity_id: Mapped[int] = mapped_column(nullable=False, comment='ID целевой сущности')
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False, comment='Тип связи lineage')
