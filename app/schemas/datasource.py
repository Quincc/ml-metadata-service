from pydantic import BaseModel, Field

from app.schemas.common import TimeStampResponseSchema


class DataSourceBase(BaseModel):
    """Базовая схема источника данных."""

    name: str = Field(..., title='Название источника')
    source_type: str = Field(..., title='Тип источника')
    location: str = Field(..., title='Путь или адрес источника')


class DataSourceCreate(DataSourceBase):
    """Схема создания источника данных."""


class DataSourceRead(DataSourceBase, TimeStampResponseSchema):
    """Схема ответа с информацией об источнике данных."""

    id: int = Field(..., title='ID источника')
