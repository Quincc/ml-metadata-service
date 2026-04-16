from pydantic import BaseModel, Field

from app.schemas.common import TimeStampResponseSchema


class DatasetVersionCreate(BaseModel):
    """Схема создания версии датасета."""

    version_number: int | None = Field(None, title='Номер версии датасета')
    schema_version_id: int | None = Field(None, title='ID связанной версии схемы')


class DatasetVersionRead(TimeStampResponseSchema):
    """Схема ответа с информацией о версии датасета."""

    id: int = Field(..., title='ID версии датасета')
    dataset_id: int = Field(..., title='ID датасета')
    version_number: int = Field(..., title='Номер версии датасета')
    schema_version_id: int | None = Field(None, title='ID версии схемы')
