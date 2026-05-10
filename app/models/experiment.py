from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimeStampMixin

EXPERIMENT_STATUSES = ("created", "running", "finished", "failed")


if TYPE_CHECKING:
    from app.models.feature_set import FeatureSet
    from app.models.model import Model


class Experiment(TimeStampMixin, Base):
    """Запуск эксперимента на наборе признаков."""

    __tablename__ = 'experiments'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment='Название эксперимента')
    feature_set_id: Mapped[int] = mapped_column(ForeignKey('feature_sets.id'), nullable=False, comment='Набор признаков')
    parameters_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment='JSON параметров эксперимента')
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, comment='JSON метрик эксперимента')
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="finished",
        server_default="finished",
        comment='Статус эксперимента: created/running/finished/failed',
    )
    notebook_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment='Ссылка на notebook')
    report_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment='Путь к отчёту')

    feature_set: Mapped[FeatureSet] = relationship(back_populates='experiments')
    models: Mapped[list[Model]] = relationship(back_populates='experiment')
