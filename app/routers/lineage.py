from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.models.lineage import LineageEdge
from app.routers import DBSession
from app.schemas.lineage import LineageCreate, LineageGraph, LineageNode, LineageRead
from app.services.lineage_service import LineageService

router = APIRouter(prefix='/lineage', tags=['lineage'])


@router.post('', response_model=LineageRead, status_code=status.HTTP_201_CREATED)
def create_lineage_edge(request: Request, db: DBSession, payload: LineageCreate) -> LineageEdge:
    """Создание связи lineage."""
    edge = LineageService.create(db=db, **payload.model_dump())
    db.commit()
    db.refresh(edge)
    return edge


@router.get('', response_model=list[LineageRead])
def list_lineage_edges(request: Request, db: DBSession) -> list[LineageEdge]:
    """Список доступных связей lineage."""
    statement = select(LineageEdge).where(LineageEdge.deleted_at.is_(None)).order_by(LineageEdge.id)
    return db.scalars(statement).all()


@router.get('/{entity_type}/{entity_id}', response_model=LineageGraph)
def get_lineage(request: Request, db: DBSession, entity_type: str, entity_id: int) -> LineageGraph:
    """Получаем lineage-граф по сущности."""
    nodes, edges = LineageService.get_graph(db=db, entity_type=entity_type, entity_id=entity_id)
    return LineageGraph(
        root_entity_type=entity_type,
        root_entity_id=entity_id,
        nodes=[LineageNode(entity_type=node_type, entity_id=node_id) for node_type, node_id in nodes],
        edges=[LineageRead.model_validate(edge) for edge in edges],
    )


@router.delete('/{edge_id}', response_model=LineageRead)
def delete_lineage_edge(request: Request, db: DBSession, edge_id: int) -> LineageEdge:
    """Мягкое удаление связи lineage."""
    edge = db.get(LineageEdge, edge_id)
    if edge is None or edge.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Lineage edge not found')

    edge.mark_deleted()
    db.commit()
    db.refresh(edge)
    return edge
