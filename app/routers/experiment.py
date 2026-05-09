from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.routers import DBSession
from app.schemas.experiment import ExperimentCreate, ExperimentRead, ExperimentStatusUpdate
from app.services.lineage_service import LineageService


router = APIRouter(prefix='/experiments', tags=['experiments'])


@router.post('', response_model=ExperimentRead, status_code=status.HTTP_201_CREATED)
def create_experiment(request: Request, db: DBSession, payload: ExperimentCreate) -> Experiment:
    """Создание эксперимента."""
    feature_set = db.get(FeatureSet, payload.feature_set_id)
    if feature_set is None or feature_set.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Feature set not found')

    experiment = Experiment(**payload.model_dump())
    db.add(experiment)
    db.flush()

    LineageService.create(
        db=db,
        from_entity_type='feature_set',
        from_entity_id=experiment.feature_set_id,
        to_entity_type='experiment',
        to_entity_id=experiment.id,
        relation_type='used_in_experiment',
    )

    db.commit()
    db.refresh(experiment)
    return experiment


@router.get('', response_model=list[ExperimentRead])
def list_experiments(request: Request, db: DBSession) -> list[Experiment]:
    """Список доступных экспериментов."""
    statement = select(Experiment).where(Experiment.deleted_at.is_(None)).order_by(Experiment.id)
    return db.scalars(statement).all()


@router.patch('/{experiment_id}/status', response_model=ExperimentRead)
def update_experiment_status(
    request: Request, db: DBSession, experiment_id: int, payload: ExperimentStatusUpdate
) -> Experiment:
    """Смена статуса эксперимента."""
    experiment = db.get(Experiment, experiment_id)
    if experiment is None or experiment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Experiment not found')

    experiment.status = payload.status
    db.commit()
    db.refresh(experiment)
    return experiment


@router.delete('/{experiment_id}', response_model=ExperimentRead)
def delete_experiment(request: Request, db: DBSession, experiment_id: int) -> Experiment:
    """Мягкое удаление эксперимента."""
    experiment = db.get(Experiment, experiment_id)
    if experiment is None or experiment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Experiment not found')

    experiment.mark_deleted()
    LineageService.remove_related_by_entity(db=db, entity_type='experiment', entity_id=experiment_id)
    db.commit()
    db.refresh(experiment)

    return experiment
