from pydantic import BaseModel, Field

from app.schemas.common import TimeStampResponseSchema


class DatasetBase(BaseModel):
    """Базовая схема датасета."""

    name: str = Field(..., title='Название датасета')
    description: str | None = Field(None, title='Описание датасета')
    source_id: int = Field(..., title='ID источника данных')


class DatasetCreate(DatasetBase):
    """Схема создания датасета."""


class DatasetRead(DatasetBase, TimeStampResponseSchema):
    """Схема ответа с информацией о датасете."""

    id: int = Field(..., title='ID датасета')
