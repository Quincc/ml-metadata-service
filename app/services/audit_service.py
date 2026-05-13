from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import attributes

from app.models.audit_log import AuditLog
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.datasource import DataSource
from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.models.model import Model
from app.models.schema_version import SchemaVersion

_AUDITABLE = (
    (DataSource, "source"),
    (Dataset, "dataset"),
    (SchemaVersion, "schema_version"),
    (DatasetVersion, "dataset_version"),
    (FeatureSet, "feature_set"),
    (Experiment, "experiment"),
    (Model, "model"),
)


def _entity_name(target) -> str | None:
    name = getattr(target, "name", None)
    if isinstance(name, str):
        return name
    version_number = getattr(target, "version_number", None)
    if version_number is not None:
        return f"v{version_number}"
    return None


def _make_audit_row(action: str, entity_type: str, target) -> dict:
    return {
        "action": action,
        "entity_type": entity_type,
        "entity_id": target.id,
        "entity_name": _entity_name(target),
    }


def register_audit_listeners() -> None:
    """Register SQLAlchemy event listeners on all auditable models."""
    for model_cls, entity_type in _AUDITABLE:
        _attach_for(model_cls, entity_type)


def _attach_for(model_cls, entity_type: str) -> None:
    @event.listens_for(model_cls, "after_insert")
    def _after_insert(mapper, connection, target):  # noqa: ARG001
        connection.execute(
            AuditLog.__table__.insert(),
            _make_audit_row("created", entity_type, target),
        )

    @event.listens_for(model_cls, "after_update")
    def _after_update(mapper, connection, target):  # noqa: ARG001
        history = attributes.get_history(target, "deleted_at")
        if not history.has_changes():
            return
        was = history.deleted[0] if history.deleted else None
        now = history.added[0] if history.added else None
        if was is None and now is not None:
            connection.execute(
                AuditLog.__table__.insert(),
                _make_audit_row("archived", entity_type, target),
            )
        elif was is not None and now is None:
            connection.execute(
                AuditLog.__table__.insert(),
                _make_audit_row("restored", entity_type, target),
            )
