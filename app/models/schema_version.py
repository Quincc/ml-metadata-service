from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimeStampMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.dataset_version import DatasetVersion


class SchemaVersion(TimeStampMixin, Base):
    """Версия схемы датасета."""

    __tablename__ = 'schema_versions'
    __table_args__ = (UniqueConstraint('dataset_id', 'version_number'),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), nullable=False, comment='Датасет')
    version_number: Mapped[int] = mapped_column(nullable=False, comment='Номер версии схемы')
    schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment='JSON-описание схемы')

    dataset: Mapped[Dataset] = relationship(back_populates='schema_versions')
    dataset_versions: Mapped[list[DatasetVersion]] = relationship(back_populates='schema_version')
