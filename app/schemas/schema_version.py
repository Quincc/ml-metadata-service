from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import TimeStampResponseSchema


class SchemaVersionCreate(BaseModel):
    """Схема создания версии схемы."""

    version_number: int | None = Field(None, title='Номер версии схемы')
    schema_definition: dict[str, Any] = Field(
        ...,
        alias='schema_json',
        title='JSON-описание схемы',
        description='Структура колонок и типов данных',
    )

    model_config = ConfigDict(populate_by_name=True)


class SchemaVersionRead(TimeStampResponseSchema):
    """Схема ответа с информацией о версии схемы."""

    id: int = Field(..., title='ID версии схемы')
    dataset_id: int = Field(..., title='ID датасета')
    version_number: int = Field(..., title='Номер версии схемы')
    schema_definition: dict[str, Any] = Field(
        ...,
        alias='schema_json',
        title='JSON-описание схемы',
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
