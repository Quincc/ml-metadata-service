from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BaseResponseSchema(BaseModel):
    """Базовая схема ответа."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TimeStampResponseSchema(BaseResponseSchema):
    """Общие поля времени для схем ответов."""

    created_at: datetime = Field(..., description='Дата создания записи')
    updated_at: datetime = Field(..., description='Дата обновления записи')
    deleted_at: datetime | None = Field(None, description='Дата мягкого удаления записи')


TimestampedRead = TimeStampResponseSchema
