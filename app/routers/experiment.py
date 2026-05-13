import json

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.datasource import DataSource
from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.models.model import Model
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


@router.get('/{experiment_id}/report', response_class=PlainTextResponse)
def export_experiment_report(request: Request, db: DBSession, experiment_id: int) -> PlainTextResponse:
    """Markdown-отчёт по эксперименту: цепочка lineage, параметры, метрики, модели."""
    experiment = db.get(Experiment, experiment_id)
    if experiment is None or experiment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Experiment not found')

    feature_set = db.get(FeatureSet, experiment.feature_set_id)
    dataset_version = db.get(DatasetVersion, feature_set.dataset_version_id) if feature_set else None
    dataset = db.get(Dataset, dataset_version.dataset_id) if dataset_version else None
    source = db.get(DataSource, dataset.source_id) if dataset else None
    models = db.scalars(
        select(Model).where(Model.experiment_id == experiment_id, Model.deleted_at.is_(None))
    ).all()

    lines = [
        f"# Experiment report: {experiment.name}",
        "",
        f"- **Status:** `{experiment.status}`",
        f"- **Created:** {experiment.local_created_at.strftime('%Y-%m-%d %H:%M') if experiment.local_created_at else '—'}",
        f"- **Notebook:** {experiment.notebook_url or '—'}",
        f"- **Report path:** {experiment.report_path or '—'}",
        "",
        "## Lineage",
        "",
        f"- Source: **{source.name if source else '—'}** (#{source.id if source else '—'})",
        f"- Dataset: **{dataset.name if dataset else '—'}** (#{dataset.id if dataset else '—'})",
        f"- Dataset version: v{dataset_version.version_number if dataset_version else '—'}",
        f"- Feature set: **{feature_set.name if feature_set else '—'}**",
        "",
        "## Parameters",
        "",
        "```json",
        json.dumps(experiment.parameters_json, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Metrics",
        "",
    ]
    if experiment.metrics_json:
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        for k, v in experiment.metrics_json.items():
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("_no metrics recorded_")
    lines.extend(["", "## Models", ""])
    if models:
        lines.append("| ID | Name | Framework | Version | Artifact |")
        lines.append("|---|---|---|---|---|")
        for m in models:
            lines.append(f"| #{m.id} | {m.name} | {m.framework or '—'} | {m.version or '—'} | {m.artifact_path or '—'} |")
    else:
        lines.append("_no models registered_")

    body = "\n".join(lines) + "\n"
    return PlainTextResponse(
        body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="experiment_{experiment_id}_report.md"'},
    )


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
