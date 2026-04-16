from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import exists, select

from app.models.dataset_version import DatasetVersion
from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.routers import DBSession
from app.schemas.feature_set import FeatureSetCreate, FeatureSetRead
from app.services.lineage_service import LineageService


router = APIRouter(prefix='/features', tags=['features'])


@router.post('', response_model=FeatureSetRead, status_code=status.HTTP_201_CREATED)
def create_feature_set(request: Request, db: DBSession, payload: FeatureSetCreate) -> FeatureSet:
    """Создание набора признаков."""
    dataset_version = db.get(DatasetVersion, payload.dataset_version_id)
    if dataset_version is None or dataset_version.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Dataset version not found')

    feature_set = FeatureSet(**payload.model_dump())
    db.add(feature_set)
    db.flush()

    LineageService.create(
        db=db,
        from_entity_type='dataset_version',
        from_entity_id=feature_set.dataset_version_id,
        to_entity_type='feature_set',
        to_entity_id=feature_set.id,
        relation_type='produces_features',
    )

    db.commit()
    db.refresh(feature_set)
    return feature_set


@router.get('', response_model=list[FeatureSetRead])
def list_feature_sets(request: Request, db: DBSession) -> list[FeatureSet]:
    """Список доступных наборов признаков."""
    statement = select(FeatureSet).where(FeatureSet.deleted_at.is_(None)).order_by(FeatureSet.id)
    return db.scalars(statement).all()


@router.delete('/{feature_set_id}', response_model=FeatureSetRead)
def delete_feature_set(request: Request, db: DBSession, feature_set_id: int) -> FeatureSet:
    """Мягкое удаление набора признаков."""
    feature_set = db.get(FeatureSet, feature_set_id)
    if feature_set is None or feature_set.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Feature set not found')

    has_experiments = db.scalar(
        select(exists().where(Experiment.feature_set_id == feature_set_id, Experiment.deleted_at.is_(None)))
    )
    if has_experiments:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Cannot delete feature set because active experiments reference it',
        )

    feature_set.mark_deleted()
    LineageService.remove_related_by_entity(db=db, entity_type='feature_set', entity_id=feature_set_id)
    db.commit()
    db.refresh(feature_set)

    return feature_set
