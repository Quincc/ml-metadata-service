from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.models.experiment import Experiment
from app.models.model import Model
from app.routers import DBSession
from app.schemas.model import ModelCreate, ModelRead
from app.services.lineage_service import LineageService


router = APIRouter(prefix='/models', tags=['models'])


@router.post('', response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def create_model(request: Request, db: DBSession, payload: ModelCreate) -> Model:
    experiment = db.get(Experiment, payload.experiment_id)
    if experiment is None or experiment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Experiment not found')

    model = Model(**payload.model_dump())
    db.add(model)
    db.flush()

    LineageService.create(
        db=db,
        from_entity_type='experiment',
        from_entity_id=model.experiment_id,
        to_entity_type='model',
        to_entity_id=model.id,
        relation_type='produces_model',
    )

    db.commit()
    db.refresh(model)
    return model


@router.get('', response_model=list[ModelRead])
def list_models(request: Request, db: DBSession) -> list[Model]:
    statement = select(Model).where(Model.deleted_at.is_(None)).order_by(Model.id)
    return db.scalars(statement).all()


@router.get('/{model_id}', response_model=ModelRead)
def get_model(request: Request, db: DBSession, model_id: int) -> Model:
    model = db.get(Model, model_id)
    if model is None or model.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Model not found')
    return model


@router.delete('/{model_id}', response_model=ModelRead)
def delete_model(request: Request, db: DBSession, model_id: int) -> Model:
    model = db.get(Model, model_id)
    if model is None or model.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Model not found')

    model.mark_deleted()
    LineageService.remove_related_by_entity(db=db, entity_type='model', entity_id=model_id)
    db.commit()
    db.refresh(model)
    return model
