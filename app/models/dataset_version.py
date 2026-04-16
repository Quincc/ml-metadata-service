from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimeStampMixin


if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.feature_set import FeatureSet
    from app.models.schema_version import SchemaVersion


class DatasetVersion(TimeStampMixin, Base):
    """Версия конкретного датасета."""

    __tablename__ = 'dataset_versions'
    __table_args__ = (UniqueConstraint('dataset_id', 'version_number'),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), nullable=False, comment='Датасет')
    version_number: Mapped[int] = mapped_column(nullable=False, comment='Номер версии датасета')
    schema_version_id: Mapped[int | None] = mapped_column(
        ForeignKey('schema_versions.id'),
        nullable=True,
        comment='Связанная версия схемы',
    )

    dataset: Mapped['Dataset'] = relationship(back_populates='versions')
    schema_version: Mapped['SchemaVersion | None'] = relationship(back_populates='dataset_versions')
    feature_sets: Mapped[list['FeatureSet']] = relationship(back_populates='dataset_version')
