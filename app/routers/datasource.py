from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import exists, select

from app.models.dataset import Dataset
from app.models.datasource import DataSource
from app.routers import DBSession
from app.schemas.datasource import DataSourceCreate, DataSourceRead
from app.services.lineage_service import LineageService


router = APIRouter(prefix='/sources', tags=['sources'])


@router.post('', response_model=DataSourceRead, status_code=status.HTTP_201_CREATED)
def create_source(request: Request, db: DBSession, payload: DataSourceCreate) -> DataSource:
    """Создание источника данных."""
    source = DataSource(**payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get('', response_model=list[DataSourceRead])
def list_sources(request: Request, db: DBSession) -> list[DataSource]:
    """Список доступных источников данных."""
    statement = select(DataSource).where(DataSource.deleted_at.is_(None)).order_by(DataSource.id)
    return db.scalars(statement).all()


@router.get('/{source_id}', response_model=DataSourceRead)
def get_source(request: Request, db: DBSession, source_id: int) -> DataSource:
    """Получаем информацию по источнику данных."""
    source = db.get(DataSource, source_id)
    if source is None or source.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Source not found')

    return source


@router.delete('/{source_id}', response_model=DataSourceRead)
def delete_source(request: Request, db: DBSession, source_id: int) -> DataSource:
    """Мягкое удаление источника данных."""
    source = db.get(DataSource, source_id)
    if source is None or source.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Source not found')

    has_datasets = db.scalar(
        select(exists().where(Dataset.source_id == source_id, Dataset.deleted_at.is_(None)))
    )
    if has_datasets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Cannot delete source because active datasets reference it',
        )

    source.mark_deleted()
    LineageService.remove_related_by_entity(db=db, entity_type='source', entity_id=source_id)
    db.commit()
    db.refresh(source)

    return source
