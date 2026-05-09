from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimeStampMixin


if TYPE_CHECKING:
    from app.models.experiment import Experiment


class Model(TimeStampMixin, Base):
    """Артефакт обученной модели, произведённый экспериментом."""

    __tablename__ = 'models'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment='Название модели')
    framework: Mapped[str | None] = mapped_column(String(64), nullable=True, comment='ML-фреймворк (xgboost, sklearn, ...)')
    version: Mapped[str | None] = mapped_column(String(64), nullable=True, comment='Версия модели')
    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment='Путь к артефакту модели')
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment='Описание модели')
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey('experiments.id'),
        nullable=False,
        comment='Эксперимент, который произвёл модель',
    )

    experiment: Mapped['Experiment'] = relationship(back_populates='models')
