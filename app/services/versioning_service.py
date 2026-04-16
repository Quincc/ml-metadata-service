from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dataset_version import DatasetVersion
from app.models.schema_version import SchemaVersion


class VersioningService:
    """Сервис по работе с версионированием датасетов и схем."""

    @classmethod
    def get_next_dataset_version(cls, db: Session, dataset_id: int) -> int:
        """Получаем следующий номер версии датасета."""
        max_version = db.scalar(
            select(func.max(DatasetVersion.version_number)).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.deleted_at.is_(None),
            )
        )
        return 1 if max_version is None else max_version + 1

    @classmethod
    def get_next_schema_version(cls, db: Session, dataset_id: int) -> int:
        """Получаем следующий номер версии схемы."""
        max_version = db.scalar(
            select(func.max(SchemaVersion.version_number)).where(
                SchemaVersion.dataset_id == dataset_id,
                SchemaVersion.deleted_at.is_(None),
            )
        )
        return 1 if max_version is None else max_version + 1


def get_next_dataset_version(db: Session, dataset_id: int) -> int:
    """Совместимость со старым функциональным стилем."""
    return VersioningService.get_next_dataset_version(db=db, dataset_id=dataset_id)


def get_next_schema_version(db: Session, dataset_id: int) -> int:
    """Совместимость со старым функциональным стилем."""
    return VersioningService.get_next_schema_version(db=db, dataset_id=dataset_id)
