from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import TimeStampResponseSchema


ExperimentStatus = Literal["created", "running", "finished", "failed"]


class ExperimentCreate(BaseModel):
    """Схема создания эксперимента."""

    name: str = Field(..., title='Название эксперимента')
    feature_set_id: int = Field(..., title='ID набора признаков')
    parameters_json: dict[str, Any] = Field(..., title='JSON параметров эксперимента')
    metrics_json: dict[str, Any] = Field(..., title='JSON метрик эксперимента')
    status: ExperimentStatus = Field(default='finished', title='Статус эксперимента')
    notebook_url: str | None = Field(default=None, title='Ссылка на notebook')
    report_path: str | None = Field(default=None, title='Путь к отчёту')


class ExperimentRead(ExperimentCreate, TimeStampResponseSchema):
    """Схема ответа с информацией об эксперименте."""

    id: int = Field(..., title='ID эксперимента')


class ExperimentStatusUpdate(BaseModel):
    """Смена статуса эксперимента."""

    status: ExperimentStatus = Field(..., title='Новый статус')
