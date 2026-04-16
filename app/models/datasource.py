from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import TimeStampMixin


if TYPE_CHECKING:
    from app.models.dataset import Dataset


class DataSource(TimeStampMixin, Base):
    """Источник данных для датасетов."""

    __tablename__ = 'data_sources'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment='Название источника')
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, comment='Тип источника данных')
    location: Mapped[str] = mapped_column(String(500), nullable=False, comment='Путь или адрес источника')

    datasets: Mapped[list['Dataset']] = relationship(back_populates='source')
