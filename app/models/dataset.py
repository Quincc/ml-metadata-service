from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimeStampMixin

if TYPE_CHECKING:
    from app.models.dataset_version import DatasetVersion
    from app.models.datasource import DataSource
    from app.models.schema_version import SchemaVersion


class Dataset(TimeStampMixin, Base):
    """Каталогизированный датасет."""

    __tablename__ = 'datasets'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment='Название датасета')
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment='Описание датасета')
    source_id: Mapped[int] = mapped_column(ForeignKey('data_sources.id'), nullable=False, comment='Источник данных')

    source: Mapped[DataSource] = relationship(back_populates='datasets')
    versions: Mapped[list[DatasetVersion]] = relationship(back_populates='dataset')
    schema_versions: Mapped[list[SchemaVersion]] = relationship(back_populates='dataset')
