from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimeStampMixin


if TYPE_CHECKING:
    from app.models.dataset_version import DatasetVersion
    from app.models.experiment import Experiment


class FeatureSet(TimeStampMixin, Base):
    """Набор признаков, собранный из версии датасета."""

    __tablename__ = 'feature_sets'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment='Название набора признаков')
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey('dataset_versions.id'),
        nullable=False,
        comment='Версия датасета',
    )
    feature_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment='JSON-описание признаков')

    dataset_version: Mapped['DatasetVersion'] = relationship(back_populates='feature_sets')
    experiments: Mapped[list['Experiment']] = relationship(back_populates='feature_set')
