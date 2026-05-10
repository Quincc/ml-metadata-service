from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from sqlalchemy import exists, select

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.datasource import DataSource
from app.models.feature_set import FeatureSet
from app.models.schema_version import SchemaVersion
from app.routers import DBSession
from app.schemas.dataset import DatasetCreate, DatasetRead
from app.schemas.dataset_version import DatasetVersionCreate, DatasetVersionRead
from app.schemas.schema_version import SchemaVersionCreate, SchemaVersionRead
from app.services.lineage_service import LineageService
from app.services.schema_inference import infer_schema_from_csv
from app.services.versioning_service import VersioningService

router = APIRouter(prefix='/datasets', tags=['datasets'])


def get_active_dataset(db: DBSession, dataset_id: int) -> Dataset:
    """Получаем активный датасет."""
    dataset = db.get(Dataset, dataset_id)
    if dataset is None or dataset.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Dataset not found')

    return dataset


@router.post('', response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
def create_dataset(request: Request, db: DBSession, payload: DatasetCreate) -> Dataset:
    """Создание датасета."""
    source = db.get(DataSource, payload.source_id)
    if source is None or source.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Source not found')

    dataset = Dataset(**payload.model_dump())
    db.add(dataset)
    db.flush()

    LineageService.create(
        db=db,
        from_entity_type='source',
        from_entity_id=dataset.source_id,
        to_entity_type='dataset',
        to_entity_id=dataset.id,
        relation_type='source_of',
    )

    db.commit()
    db.refresh(dataset)
    return dataset


@router.get('', response_model=list[DatasetRead])
def list_datasets(request: Request, db: DBSession) -> list[Dataset]:
    """Список доступных датасетов."""
    statement = select(Dataset).where(Dataset.deleted_at.is_(None)).order_by(Dataset.id)
    return db.scalars(statement).all()


@router.get('/{dataset_id}', response_model=DatasetRead)
def get_dataset(request: Request, db: DBSession, dataset_id: int) -> Dataset:
    """Получаем информацию по датасету."""
    return get_active_dataset(db=db, dataset_id=dataset_id)


@router.delete('/{dataset_id}', response_model=DatasetRead)
def delete_dataset(request: Request, db: DBSession, dataset_id: int) -> Dataset:
    """Мягкое удаление датасета."""
    dataset = get_active_dataset(db=db, dataset_id=dataset_id)

    has_versions = db.scalar(
        select(exists().where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.deleted_at.is_(None)))
    )
    has_schema_versions = db.scalar(
        select(exists().where(SchemaVersion.dataset_id == dataset_id, SchemaVersion.deleted_at.is_(None)))
    )
    if has_versions or has_schema_versions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Cannot delete dataset because active versions or schema versions reference it',
        )

    dataset.mark_deleted()
    LineageService.remove_related_by_entity(db=db, entity_type='dataset', entity_id=dataset_id)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.post('/{dataset_id}/versions', response_model=DatasetVersionRead, status_code=status.HTTP_201_CREATED)
def create_dataset_version(
    request: Request,
    db: DBSession,
    dataset_id: int,
    payload: DatasetVersionCreate,
) -> DatasetVersion:
    """Создание версии датасета."""
    get_active_dataset(db=db, dataset_id=dataset_id)

    if payload.schema_version_id is not None:
        schema_version = db.get(SchemaVersion, payload.schema_version_id)
        if schema_version is None or schema_version.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Schema version not found')
        if schema_version.dataset_id != dataset_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Schema version belongs to another dataset',
            )

    version_number = payload.version_number or VersioningService.get_next_dataset_version(db=db, dataset_id=dataset_id)
    version = DatasetVersion(
        dataset_id=dataset_id,
        version_number=version_number,
        schema_version_id=payload.schema_version_id,
    )
    db.add(version)
    db.flush()

    LineageService.create(
        db=db,
        from_entity_type='dataset',
        from_entity_id=dataset_id,
        to_entity_type='dataset_version',
        to_entity_id=version.id,
        relation_type='has_version',
    )

    if payload.schema_version_id is not None:
        LineageService.create(
            db=db,
            from_entity_type='schema_version',
            from_entity_id=payload.schema_version_id,
            to_entity_type='dataset_version',
            to_entity_id=version.id,
            relation_type='defines_schema_for',
        )

    db.commit()
    db.refresh(version)
    return version


@router.get('/{dataset_id}/versions', response_model=list[DatasetVersionRead])
def list_dataset_versions(request: Request, db: DBSession, dataset_id: int) -> list[DatasetVersion]:
    """Список версий датасета."""
    get_active_dataset(db=db, dataset_id=dataset_id)

    statement = (
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.deleted_at.is_(None))
        .order_by(DatasetVersion.version_number)
    )
    return db.scalars(statement).all()


@router.delete('/{dataset_id}/versions/{version_id}', response_model=DatasetVersionRead)
def delete_dataset_version(request: Request, db: DBSession, dataset_id: int, version_id: int) -> DatasetVersion:
    """Мягкое удаление версии датасета."""
    get_active_dataset(db=db, dataset_id=dataset_id)

    version = db.get(DatasetVersion, version_id)
    if version is None or version.deleted_at is not None or version.dataset_id != dataset_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Dataset version not found')

    has_feature_sets = db.scalar(
        select(exists().where(FeatureSet.dataset_version_id == version_id, FeatureSet.deleted_at.is_(None)))
    )
    if has_feature_sets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Cannot delete dataset version because active feature sets reference it',
        )

    version.mark_deleted()
    LineageService.remove_related_by_entity(db=db, entity_type='dataset_version', entity_id=version_id)
    db.commit()
    db.refresh(version)
    return version


@router.post('/{dataset_id}/schema', response_model=SchemaVersionRead, status_code=status.HTTP_201_CREATED)
def create_schema_version(
    request: Request,
    db: DBSession,
    dataset_id: int,
    payload: SchemaVersionCreate,
) -> SchemaVersion:
    """Создание версии схемы датасета."""
    get_active_dataset(db=db, dataset_id=dataset_id)

    version_number = payload.version_number or VersioningService.get_next_schema_version(db=db, dataset_id=dataset_id)
    schema_version = SchemaVersion(
        dataset_id=dataset_id,
        version_number=version_number,
        schema_json=payload.schema_definition,
    )
    db.add(schema_version)
    db.flush()

    LineageService.create(
        db=db,
        from_entity_type='dataset',
        from_entity_id=dataset_id,
        to_entity_type='schema_version',
        to_entity_id=schema_version.id,
        relation_type='has_schema_version',
    )

    db.commit()
    db.refresh(schema_version)
    return schema_version


@router.post('/{dataset_id}/schema/from-csv', response_model=SchemaVersionRead, status_code=status.HTTP_201_CREATED)
def create_schema_version_from_csv(
    request: Request,
    db: DBSession,
    dataset_id: int,
    file: UploadFile = File(...),
) -> SchemaVersion:
    """Создание версии схемы автоматически из CSV-файла."""
    get_active_dataset(db=db, dataset_id=dataset_id)

    file_bytes = file.file.read()
    schema_definition = infer_schema_from_csv(file_bytes)

    version_number = VersioningService.get_next_schema_version(db=db, dataset_id=dataset_id)
    schema_version = SchemaVersion(
        dataset_id=dataset_id,
        version_number=version_number,
        schema_json=schema_definition,
    )
    db.add(schema_version)
    db.flush()

    LineageService.create(
        db=db,
        from_entity_type='dataset',
        from_entity_id=dataset_id,
        to_entity_type='schema_version',
        to_entity_id=schema_version.id,
        relation_type='has_schema_version',
    )

    db.commit()
    db.refresh(schema_version)
    return schema_version


@router.get('/{dataset_id}/schema', response_model=list[SchemaVersionRead])
def list_schema_versions(request: Request, db: DBSession, dataset_id: int) -> list[SchemaVersion]:
    """Список версий схемы для датасета."""
    get_active_dataset(db=db, dataset_id=dataset_id)

    statement = (
        select(SchemaVersion)
        .where(SchemaVersion.dataset_id == dataset_id, SchemaVersion.deleted_at.is_(None))
        .order_by(SchemaVersion.version_number)
    )
    return db.scalars(statement).all()


@router.delete('/{dataset_id}/schema/{schema_version_id}', response_model=SchemaVersionRead)
def delete_schema_version(
    request: Request,
    db: DBSession,
    dataset_id: int,
    schema_version_id: int,
) -> SchemaVersion:
    """Мягкое удаление версии схемы."""
    get_active_dataset(db=db, dataset_id=dataset_id)

    schema_version = db.get(SchemaVersion, schema_version_id)
    if schema_version is None or schema_version.deleted_at is not None or schema_version.dataset_id != dataset_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Schema version not found')

    in_use = db.scalar(
        select(
            exists().where(
                DatasetVersion.schema_version_id == schema_version_id,
                DatasetVersion.deleted_at.is_(None),
            )
        )
    )
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Cannot delete schema version because active dataset versions reference it',
        )

    schema_version.mark_deleted()
    LineageService.remove_related_by_entity(db=db, entity_type='schema_version', entity_id=schema_version_id)
    db.commit()
    db.refresh(schema_version)
    return schema_version
