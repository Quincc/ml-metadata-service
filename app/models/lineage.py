from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import TimeStampMixin


class LineageEdge(TimeStampMixin, Base):
    """Связь происхождения данных между двумя сущностями."""

    __tablename__ = 'lineage_edges'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    from_entity_type: Mapped[str] = mapped_column(String(100), nullable=False, comment='Тип исходной сущности')
    from_entity_id: Mapped[int] = mapped_column(nullable=False, comment='ID исходной сущности')
    to_entity_type: Mapped[str] = mapped_column(String(100), nullable=False, comment='Тип целевой сущности')
    to_entity_id: Mapped[int] = mapped_column(nullable=False, comment='ID целевой сущности')
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False, comment='Тип связи lineage')
