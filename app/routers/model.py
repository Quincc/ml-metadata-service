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
from app.models.schema_version import SchemaVersion
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



@router.get('/{model_id}/pipeline-report', response_class=PlainTextResponse)
def export_model_pipeline_report(request: Request, db: DBSession, model_id: int) -> PlainTextResponse:
    """Markdown-отчёт по полной цепочке source -> dataset -> feature set -> experiment -> model."""
    model = db.get(Model, model_id)
    if model is None or model.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Model not found')

    experiment = db.get(Experiment, model.experiment_id)
    feature_set = db.get(FeatureSet, experiment.feature_set_id) if experiment else None
    dataset_version = db.get(DatasetVersion, feature_set.dataset_version_id) if feature_set else None
    schema_version = db.get(SchemaVersion, dataset_version.schema_version_id) if dataset_version and dataset_version.schema_version_id else None
    dataset = db.get(Dataset, dataset_version.dataset_id) if dataset_version else None
    source = db.get(DataSource, dataset.source_id) if dataset else None

    lines = [
        f"# Pipeline report: {model.name}",
        "",
        "## Pipeline chain",
        "",
        f"- Source: **{source.name if source else '—'}** (#{source.id if source else '—'}, {source.source_type if source else '—'})",
        f"- Dataset: **{dataset.name if dataset else '—'}** (#{dataset.id if dataset else '—'})",
        f"- Schema version: v{schema_version.version_number if schema_version else '—'} (#{schema_version.id if schema_version else '—'})",
        f"- Dataset version: v{dataset_version.version_number if dataset_version else '—'} (#{dataset_version.id if dataset_version else '—'})",
        f"- Feature set: **{feature_set.name if feature_set else '—'}** (#{feature_set.id if feature_set else '—'})",
        f"- Experiment: **{experiment.name if experiment else '—'}** (#{experiment.id if experiment else '—'})",
        f"- Model: **{model.name}** (#{model.id})",
        "",
        "## Model",
        "",
        f"- Framework: {model.framework or '—'}",
        f"- Version: {model.version or '—'}",
        f"- Artifact path: {model.artifact_path or '—'}",
        f"- Description: {model.description or '—'}",
        "",
        "## Experiment",
        "",
        f"- Status: {experiment.status if experiment else '—'}",
        f"- Notebook: {experiment.notebook_url if experiment else '—'}",
        f"- Report path: {experiment.report_path if experiment else '—'}",
        "",
        "### Parameters",
        "",
        "```json",
        json.dumps(experiment.parameters_json if experiment else {}, indent=2, ensure_ascii=False),
        "```",
        "",
        "### Metrics",
        "",
    ]

    if experiment and experiment.metrics_json:
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        for key, value in experiment.metrics_json.items():
            lines.append(f"| {key} | {value} |")
    else:
        lines.append("_no metrics recorded_")

    lines.extend(["", "## Feature schema", "", "```json", json.dumps(feature_set.feature_schema_json if feature_set else {}, indent=2, ensure_ascii=False), "```"])
    lines.extend(["", "## Data schema", "", "```json", json.dumps(schema_version.schema_json if schema_version else {}, indent=2, ensure_ascii=False), "```"])

    body = "\n".join(lines) + "\n"
    return PlainTextResponse(
        body,
        media_type='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="model_{model_id}_pipeline_report.md"'},
    )

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
