from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import TimeStampResponseSchema


class ModelCreate(BaseModel):
    """Схема создания модели."""

    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(..., title='Название модели')
    experiment_id: int = Field(..., title='ID эксперимента, который произвёл модель')
    framework: str | None = Field(default=None, title='ML-фреймворк')
    version: str | None = Field(default=None, title='Версия модели')
    artifact_path: str | None = Field(default=None, title='Путь к артефакту модели')
    description: str | None = Field(default=None, title='Описание модели')


class ModelRead(ModelCreate, TimeStampResponseSchema):
    """Схема ответа с информацией о модели."""

    id: int = Field(..., title='ID модели')
