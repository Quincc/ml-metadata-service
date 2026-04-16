from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import TimeStampResponseSchema


class FeatureSetCreate(BaseModel):
    """Схема создания набора признаков."""

    name: str = Field(..., title='Название набора признаков')
    dataset_version_id: int = Field(..., title='ID версии датасета')
    feature_schema_json: dict[str, Any] = Field(..., title='JSON-описание признаков')


class FeatureSetRead(FeatureSetCreate, TimeStampResponseSchema):
    """Схема ответа с информацией о наборе признаков."""

    id: int = Field(..., title='ID набора признаков')
