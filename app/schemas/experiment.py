from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import TimeStampResponseSchema


class ExperimentCreate(BaseModel):
    """Схема создания эксперимента."""

    name: str = Field(..., title='Название эксперимента')
    feature_set_id: int = Field(..., title='ID набора признаков')
    parameters_json: dict[str, Any] = Field(..., title='JSON параметров эксперимента')
    metrics_json: dict[str, Any] = Field(..., title='JSON метрик эксперимента')


class ExperimentRead(ExperimentCreate, TimeStampResponseSchema):
    """Схема ответа с информацией об эксперименте."""

    id: int = Field(..., title='ID эксперимента')
