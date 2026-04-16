from pydantic import BaseModel, Field

from app.schemas.common import TimeStampResponseSchema


class LineageCreate(BaseModel):
    """Схема создания связи lineage."""

    from_entity_type: str = Field(..., title='Тип исходной сущности')
    from_entity_id: int = Field(..., title='ID исходной сущности')
    to_entity_type: str = Field(..., title='Тип целевой сущности')
    to_entity_id: int = Field(..., title='ID целевой сущности')
    relation_type: str = Field(..., title='Тип связи')


class LineageRead(LineageCreate, TimeStampResponseSchema):
    """Схема ответа с информацией о lineage-связи."""

    id: int = Field(..., title='ID связи lineage')


class LineageNode(BaseModel):
    """Узел lineage-графа."""

    entity_type: str = Field(..., title='Тип сущности')
    entity_id: int = Field(..., title='ID сущности')


class LineageGraph(BaseModel):
    """Полный граф lineage для выбранной сущности."""

    root_entity_type: str = Field(..., title='Тип корневой сущности')
    root_entity_id: int = Field(..., title='ID корневой сущности')
    nodes: list[LineageNode] = Field(default_factory=list, title='Список узлов графа')
    edges: list[LineageRead] = Field(default_factory=list, title='Список связей графа')
