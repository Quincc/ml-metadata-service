import json
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.datasource import DataSource
from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.models.model import Model
from app.models.schema_version import SchemaVersion
from app.routers import DBSession
from app.schemas.lineage import LineageGraph, LineageNode, LineageRead
from app.services.lineage_service import LineageService
from app.services.schema_inference import infer_schema_from_csv
from app.services.versioning_service import VersioningService

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory="app/templates")

LINEAGE_ENTITY_TYPES = [
    "source",
    "dataset",
    "schema_version",
    "dataset_version",
    "feature_set",
    "experiment",
    "model",
]

SOURCE_TYPE_OPTIONS = [
    "csv",
    "parquet",
    "postgresql",
    "mysql",
    "s3",
    "api",
    "filesystem",
]


def _parse_json_field(value: str, field_name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Field '{field_name}' must contain valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Field '{field_name}' must be a JSON object")

    return parsed


def _parse_optional_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    return int(value)


def _load_dashboard_data(db: DBSession) -> dict[str, Any]:
    sources = db.scalars(
        select(DataSource).where(DataSource.deleted_at.is_(None)).order_by(DataSource.id.desc())
    ).all()
    datasets = db.scalars(
        select(Dataset).where(Dataset.deleted_at.is_(None)).order_by(Dataset.id.desc())
    ).all()
    schema_versions = db.scalars(
        select(SchemaVersion).where(SchemaVersion.deleted_at.is_(None)).order_by(SchemaVersion.id.desc())
    ).all()
    dataset_versions = db.scalars(
        select(DatasetVersion).where(DatasetVersion.deleted_at.is_(None)).order_by(DatasetVersion.id.desc())
    ).all()
    feature_sets = db.scalars(
        select(FeatureSet).where(FeatureSet.deleted_at.is_(None)).order_by(FeatureSet.id.desc())
    ).all()
    experiments = db.scalars(
        select(Experiment).where(Experiment.deleted_at.is_(None)).order_by(Experiment.id.desc())
    ).all()
    models = db.scalars(
        select(Model).where(Model.deleted_at.is_(None)).order_by(Model.id.desc())
    ).all()

    return {
        "sources": sources,
        "datasets": datasets,
        "schema_versions": schema_versions,
        "dataset_versions": dataset_versions,
        "feature_sets": feature_sets,
        "experiments": experiments,
        "models": models,
        "counts": {
            "sources": len(sources),
            "datasets": len(datasets),
            "schema_versions": len(schema_versions),
            "dataset_versions": len(dataset_versions),
            "feature_sets": len(feature_sets),
            "experiments": len(experiments),
            "models": len(models),
        },
        "source_lookup": {source.id: source.name for source in sources},
        "dataset_lookup": {dataset.id: dataset.name for dataset in datasets},
        "schema_lookup": {
            schema_version.id: f"{schema_version.dataset_id} / schema v{schema_version.version_number}"
            for schema_version in schema_versions
        },
        "dataset_version_lookup": {
            version.id: f"{version.dataset_id} / dataset v{version.version_number}"
            for version in dataset_versions
        },
        "feature_lookup": {feature_set.id: feature_set.name for feature_set in feature_sets},
        "experiment_lookup": {experiment.id: experiment.name for experiment in experiments},
        "model_lookup": {model.id: model.name for model in models},
        "lineage_entity_types": LINEAGE_ENTITY_TYPES,
        "source_type_options": SOURCE_TYPE_OPTIONS,
    }


def _render_dashboard(
    request: Request,
    db: DBSession,
    *,
    message: str | None = None,
    error: str | None = None,
    lineage_graph: LineageGraph | None = None,
    lineage_error: str | None = None,
    selected_entity_type: str = "dataset",
    selected_entity_id: int | None = None,
    partial: str = "dashboard",
) -> HTMLResponse:
    context = {
        "request": request,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": lineage_error,
        "selected_entity_type": selected_entity_type,
        "selected_entity_id": selected_entity_id,
        **_load_dashboard_data(db),
    }
    template_map = {
        "full": "ui/index.html.j2",
        "dashboard": "ui/_dashboard_content.html.j2",
        "lineage": "ui/_lineage_section.html.j2",
    }
    return templates.TemplateResponse(template_map[partial], context)


def _commit_or_rollback(db: DBSession) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Object with the same unique fields already exists") from exc


def _handle_ui_error(db: DBSession, exc: Exception) -> str:
    if isinstance(exc, IntegrityError):
        db.rollback()
        return "Object with the same unique fields already exists"
    return str(exc)


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, db: DBSession) -> HTMLResponse:
    return _render_dashboard(request, db, partial="full")


@router.post("/sources", response_class=HTMLResponse)
def create_source_ui(
    request: Request,
    db: DBSession,
    name: str = Form(...),
    source_type: str = Form(...),
    location: str = Form(...),
) -> HTMLResponse:
    try:
        source = DataSource(name=name, source_type=source_type, location=location)
        db.add(source)
        _commit_or_rollback(db)
        return _render_dashboard(request, db, message=f"Source '{name}' created successfully")
    except (ValueError, IntegrityError) as exc:
        return _render_dashboard(request, db, error=_handle_ui_error(db, exc))


@router.post("/datasets", response_class=HTMLResponse)
def create_dataset_ui(
    request: Request,
    db: DBSession,
    name: str = Form(...),
    description: str = Form(""),
    source_id: int = Form(...),
) -> HTMLResponse:
    source = db.get(DataSource, source_id)
    if source is None:
        return _render_dashboard(request, db, error="Selected source does not exist")

    try:
        dataset = Dataset(
            name=name,
            description=description or None,
            source_id=source_id,
        )
        db.add(dataset)
        db.flush()
        LineageService.create(
            db=db,
            from_entity_type="source",
            from_entity_id=source_id,
            to_entity_type="dataset",
            to_entity_id=dataset.id,
            relation_type="source_of",
        )
        _commit_or_rollback(db)
        return _render_dashboard(request, db, message=f"Dataset '{name}' created successfully")
    except (ValueError, IntegrityError) as exc:
        return _render_dashboard(request, db, error=_handle_ui_error(db, exc))


@router.post("/schema-versions", response_class=HTMLResponse)
def create_schema_version_ui(
    request: Request,
    db: DBSession,
    dataset_id: int = Form(...),
    version_number: str = Form(""),
    schema_json: str = Form(...),
) -> HTMLResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        return _render_dashboard(request, db, error="Selected dataset does not exist")

    try:
        schema_payload = _parse_json_field(schema_json, "schema_json")
        schema_version = SchemaVersion(
            dataset_id=dataset_id,
            version_number=_parse_optional_int(version_number)
            or VersioningService.get_next_schema_version(db=db, dataset_id=dataset_id),
            schema_json=schema_payload,
        )
        db.add(schema_version)
        db.flush()
        LineageService.create(
            db=db,
            from_entity_type="dataset",
            from_entity_id=dataset_id,
            to_entity_type="schema_version",
            to_entity_id=schema_version.id,
            relation_type="has_schema_version",
        )
        _commit_or_rollback(db)
        return _render_dashboard(
            request,
            db,
            message=f"Schema version for dataset '{dataset.name}' created successfully",
        )
    except (ValueError, IntegrityError) as exc:
        return _render_dashboard(request, db, error=_handle_ui_error(db, exc))


@router.post("/dataset-versions", response_class=HTMLResponse)
def create_dataset_version_ui(
    request: Request,
    db: DBSession,
    dataset_id: int = Form(...),
    version_number: str = Form(""),
    schema_version_id: str = Form(""),
) -> HTMLResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        return _render_dashboard(request, db, error="Selected dataset does not exist")

    try:
        schema_id = _parse_optional_int(schema_version_id)
        if schema_id is not None:
            schema_version = db.get(SchemaVersion, schema_id)
            if schema_version is None:
                raise ValueError("Selected schema version does not exist")
            if schema_version.dataset_id != dataset_id:
                raise ValueError("Schema version belongs to another dataset")

        dataset_version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=_parse_optional_int(version_number)
            or VersioningService.get_next_dataset_version(db=db, dataset_id=dataset_id),
            schema_version_id=schema_id,
        )
        db.add(dataset_version)
        db.flush()
        LineageService.create(
            db=db,
            from_entity_type="dataset",
            from_entity_id=dataset_id,
            to_entity_type="dataset_version",
            to_entity_id=dataset_version.id,
            relation_type="has_version",
        )
        if schema_id is not None:
            LineageService.create(
                db=db,
                from_entity_type="schema_version",
                from_entity_id=schema_id,
                to_entity_type="dataset_version",
                to_entity_id=dataset_version.id,
                relation_type="defines_schema_for",
            )
        _commit_or_rollback(db)
        return _render_dashboard(
            request,
            db,
            message=f"Dataset version for '{dataset.name}' created successfully",
        )
    except (ValueError, IntegrityError) as exc:
        return _render_dashboard(request, db, error=_handle_ui_error(db, exc))


@router.post("/feature-sets", response_class=HTMLResponse)
def create_feature_set_ui(
    request: Request,
    db: DBSession,
    name: str = Form(...),
    dataset_version_id: int = Form(...),
    feature_schema_json: str = Form(...),
) -> HTMLResponse:
    dataset_version = db.get(DatasetVersion, dataset_version_id)
    if dataset_version is None:
        return _render_dashboard(request, db, error="Selected dataset version does not exist")

    try:
        feature_set = FeatureSet(
            name=name,
            dataset_version_id=dataset_version_id,
            feature_schema_json=_parse_json_field(feature_schema_json, "feature_schema_json"),
        )
        db.add(feature_set)
        db.flush()
        LineageService.create(
            db=db,
            from_entity_type="dataset_version",
            from_entity_id=dataset_version_id,
            to_entity_type="feature_set",
            to_entity_id=feature_set.id,
            relation_type="produces_features",
        )
        _commit_or_rollback(db)
        return _render_dashboard(request, db, message=f"Feature set '{name}' created successfully")
    except (ValueError, IntegrityError) as exc:
        return _render_dashboard(request, db, error=_handle_ui_error(db, exc))


@router.post("/experiments", response_class=HTMLResponse)
def create_experiment_ui(
    request: Request,
    db: DBSession,
    name: str = Form(...),
    feature_set_id: int = Form(...),
    parameters_json: str = Form(...),
    metrics_json: str = Form(...),
) -> HTMLResponse:
    feature_set = db.get(FeatureSet, feature_set_id)
    if feature_set is None:
        return _render_dashboard(request, db, error="Selected feature set does not exist")

    try:
        experiment = Experiment(
            name=name,
            feature_set_id=feature_set_id,
            parameters_json=_parse_json_field(parameters_json, "parameters_json"),
            metrics_json=_parse_json_field(metrics_json, "metrics_json"),
        )
        db.add(experiment)
        db.flush()
        LineageService.create(
            db=db,
            from_entity_type="feature_set",
            from_entity_id=feature_set_id,
            to_entity_type="experiment",
            to_entity_id=experiment.id,
            relation_type="used_in_experiment",
        )
        _commit_or_rollback(db)
        return _render_dashboard(request, db, message=f"Experiment '{name}' created successfully")
    except (ValueError, IntegrityError) as exc:
        return _render_dashboard(request, db, error=_handle_ui_error(db, exc))


@router.post("/models", response_class=HTMLResponse)
def create_model_ui(
    request: Request,
    db: DBSession,
    name: str = Form(...),
    experiment_id: int = Form(...),
    framework: str = Form(""),
    version: str = Form(""),
    artifact_path: str = Form(""),
) -> HTMLResponse:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return _render_dashboard(request, db, error="Selected experiment does not exist")

    try:
        model = Model(
            name=name,
            experiment_id=experiment_id,
            framework=framework or None,
            version=version or None,
            artifact_path=artifact_path or None,
        )
        db.add(model)
        db.flush()
        LineageService.create(
            db=db,
            from_entity_type="experiment",
            from_entity_id=experiment_id,
            to_entity_type="model",
            to_entity_id=model.id,
            relation_type="produces_model",
        )
        _commit_or_rollback(db)
        return _render_dashboard(request, db, message=f"Model '{name}' registered successfully")
    except (ValueError, IntegrityError) as exc:
        return _render_dashboard(request, db, error=_handle_ui_error(db, exc))


@router.get("/lineage", response_class=HTMLResponse)
def view_lineage_ui(
    request: Request,
    db: DBSession,
    entity_type: str,
    entity_id: int,
) -> HTMLResponse:
    if entity_type not in LINEAGE_ENTITY_TYPES:
        return _render_dashboard(
            request,
            db,
            lineage_error="Unsupported entity type for lineage lookup",
            selected_entity_type=entity_type,
            selected_entity_id=entity_id,
            partial="lineage",
        )

    nodes, edges = LineageService.get_graph(db=db, entity_type=entity_type, entity_id=entity_id)
    lineage_graph = LineageGraph(
        root_entity_type=entity_type,
        root_entity_id=entity_id,
        nodes=[LineageNode(entity_type=node_type, entity_id=node_id) for node_type, node_id in nodes],
        edges=[LineageRead.model_validate(edge) for edge in edges],
    )
    return _render_dashboard(
        request,
        db,
        lineage_graph=lineage_graph,
        selected_entity_type=entity_type,
        selected_entity_id=entity_id,
        partial="lineage",
    )


def _build_lineage_graph(db: DBSession, entity_type: str, entity_id: int) -> LineageGraph:
    nodes, edges = LineageService.get_graph(db=db, entity_type=entity_type, entity_id=entity_id)
    return LineageGraph(
        root_entity_type=entity_type,
        root_entity_id=entity_id,
        nodes=[LineageNode(entity_type=node_type, entity_id=node_id) for node_type, node_id in nodes],
        edges=[LineageRead.model_validate(edge) for edge in edges],
    )


@router.get("/datasets/{dataset_id}", response_class=HTMLResponse)
def dataset_detail(
    request: Request,
    db: DBSession,
    dataset_id: int,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        return _render_dashboard(
            request, db, error=f"Dataset #{dataset_id} not found", partial="full"
        )

    schema_versions = db.scalars(
        select(SchemaVersion)
        .where(SchemaVersion.dataset_id == dataset_id)
        .order_by(SchemaVersion.version_number.desc())
    ).all()
    dataset_versions = db.scalars(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version_number.desc())
    ).all()
    feature_sets = []
    if dataset_versions:
        version_ids = [v.id for v in dataset_versions]
        feature_sets = db.scalars(
            select(FeatureSet)
            .where(FeatureSet.dataset_version_id.in_(version_ids))
            .order_by(FeatureSet.id.desc())
        ).all()
    source = db.get(DataSource, dataset.source_id)
    lineage_graph = _build_lineage_graph(db, "dataset", dataset_id)

    context = {
        "request": request,
        "dataset": dataset,
        "source": source,
        "schema_versions": schema_versions,
        "dataset_versions": dataset_versions,
        "feature_sets": feature_sets,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": None,
        "selected_entity_type": "dataset",
        "selected_entity_id": dataset_id,
        **_load_dashboard_data(db),
    }
    return templates.TemplateResponse("ui/dataset_detail.html.j2", context)


@router.post("/datasets/{dataset_id}/schema/from-csv")
def create_schema_from_csv_ui(
    db: DBSession,
    dataset_id: int,
    file: UploadFile = File(...),
) -> RedirectResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        return RedirectResponse(url="/ui", status_code=303)
    try:
        schema_definition = infer_schema_from_csv(file.file.read())
    except ValueError:
        return RedirectResponse(url=f"/ui/datasets/{dataset_id}?error=Invalid+CSV", status_code=303)

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
        from_entity_type="dataset",
        from_entity_id=dataset_id,
        to_entity_type="schema_version",
        to_entity_id=schema_version.id,
        relation_type="has_schema_version",
    )
    db.commit()
    return RedirectResponse(
        url=f"/ui/datasets/{dataset_id}?message=Schema+v{version_number}+inferred+from+CSV",
        status_code=303,
    )


@router.post("/datasets/{dataset_id}/versions/from-csv")
def create_dataset_version_from_csv_ui(
    db: DBSession,
    dataset_id: int,
    file: UploadFile = File(...),
) -> RedirectResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        return RedirectResponse(url="/ui", status_code=303)
    try:
        schema_definition = infer_schema_from_csv(file.file.read())
    except ValueError:
        return RedirectResponse(url=f"/ui/datasets/{dataset_id}?error=Invalid+CSV", status_code=303)

    schema_version = SchemaVersion(
        dataset_id=dataset_id,
        version_number=VersioningService.get_next_schema_version(db=db, dataset_id=dataset_id),
        schema_json=schema_definition,
    )
    db.add(schema_version)
    db.flush()
    LineageService.create(
        db=db, from_entity_type="dataset", from_entity_id=dataset_id,
        to_entity_type="schema_version", to_entity_id=schema_version.id,
        relation_type="has_schema_version",
    )
    dataset_version = DatasetVersion(
        dataset_id=dataset_id,
        version_number=VersioningService.get_next_dataset_version(db=db, dataset_id=dataset_id),
        schema_version_id=schema_version.id,
    )
    db.add(dataset_version)
    db.flush()
    LineageService.create(
        db=db, from_entity_type="dataset", from_entity_id=dataset_id,
        to_entity_type="dataset_version", to_entity_id=dataset_version.id,
        relation_type="has_version",
    )
    LineageService.create(
        db=db, from_entity_type="schema_version", from_entity_id=schema_version.id,
        to_entity_type="dataset_version", to_entity_id=dataset_version.id,
        relation_type="defines_schema_for",
    )
    db.commit()
    return RedirectResponse(
        url=f"/ui/datasets/{dataset_id}?message=Imported+CSV:+schema+v{schema_version.version_number}+%2B+version+v{dataset_version.version_number}",
        status_code=303,
    )


@router.post("/datasets/{dataset_id}/delete")
def delete_dataset_ui(db: DBSession, dataset_id: int) -> RedirectResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        return RedirectResponse(url="/ui", status_code=303)
    if dataset.deleted_at is None:
        dataset.mark_deleted()
        db.commit()
    return RedirectResponse(url=f"/ui/datasets/{dataset_id}", status_code=303)


@router.post("/datasets/{dataset_id}/restore")
def restore_dataset_ui(db: DBSession, dataset_id: int) -> RedirectResponse:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        return RedirectResponse(url="/ui", status_code=303)
    if dataset.deleted_at is not None:
        dataset.restore()
        db.commit()
    return RedirectResponse(url=f"/ui/datasets/{dataset_id}", status_code=303)


@router.get("/experiments/{experiment_id}", response_class=HTMLResponse)
def experiment_detail(
    request: Request,
    db: DBSession,
    experiment_id: int,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return _render_dashboard(
            request, db, error=f"Experiment #{experiment_id} not found", partial="full"
        )

    feature_set = db.get(FeatureSet, experiment.feature_set_id)
    dataset_version = (
        db.get(DatasetVersion, feature_set.dataset_version_id) if feature_set else None
    )
    dataset = db.get(Dataset, dataset_version.dataset_id) if dataset_version else None
    lineage_graph = _build_lineage_graph(db, "experiment", experiment_id)

    context = {
        "request": request,
        "experiment": experiment,
        "feature_set": feature_set,
        "dataset_version": dataset_version,
        "dataset": dataset,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": None,
        "selected_entity_type": "experiment",
        "selected_entity_id": experiment_id,
        **_load_dashboard_data(db),
    }
    return templates.TemplateResponse("ui/experiment_detail.html.j2", context)


@router.post("/experiments/{experiment_id}/delete")
def delete_experiment_ui(db: DBSession, experiment_id: int) -> RedirectResponse:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return RedirectResponse(url="/ui", status_code=303)
    if experiment.deleted_at is None:
        experiment.mark_deleted()
        db.commit()
    return RedirectResponse(url=f"/ui/experiments/{experiment_id}", status_code=303)


@router.post("/experiments/{experiment_id}/status")
def update_experiment_status_ui(
    db: DBSession, experiment_id: int, status: str = Form(...)
) -> RedirectResponse:
    if status not in ("created", "running", "finished", "failed"):
        return RedirectResponse(url=f"/ui/experiments/{experiment_id}", status_code=303)
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return RedirectResponse(url="/ui", status_code=303)
    experiment.status = status
    db.commit()
    return RedirectResponse(url=f"/ui/experiments/{experiment_id}", status_code=303)


_ENTITY_MODELS = {
    "source": DataSource,
    "dataset": Dataset,
    "schema_version": SchemaVersion,
    "dataset_version": DatasetVersion,
    "feature_set": FeatureSet,
    "experiment": Experiment,
    "model": Model,
}


def _archived_rows(db: DBSession) -> dict[str, list[dict]]:
    def fmt(dt) -> str:
        return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"

    sources = db.scalars(
        select(DataSource).where(DataSource.deleted_at.is_not(None)).order_by(DataSource.id.desc())
    ).all()
    datasets = db.scalars(
        select(Dataset).where(Dataset.deleted_at.is_not(None)).order_by(Dataset.id.desc())
    ).all()
    schema_versions = db.scalars(
        select(SchemaVersion).where(SchemaVersion.deleted_at.is_not(None)).order_by(SchemaVersion.id.desc())
    ).all()
    dataset_versions = db.scalars(
        select(DatasetVersion).where(DatasetVersion.deleted_at.is_not(None)).order_by(DatasetVersion.id.desc())
    ).all()
    feature_sets = db.scalars(
        select(FeatureSet).where(FeatureSet.deleted_at.is_not(None)).order_by(FeatureSet.id.desc())
    ).all()
    experiments = db.scalars(
        select(Experiment).where(Experiment.deleted_at.is_not(None)).order_by(Experiment.id.desc())
    ).all()
    models = db.scalars(
        select(Model).where(Model.deleted_at.is_not(None)).order_by(Model.id.desc())
    ).all()

    return {
        "sources": [
            {"type": "source", "id": s.id, "cells": [f"#{s.id}", s.name, s.source_type], "deleted_at": fmt(s.local_deleted_at)}
            for s in sources
        ],
        "datasets": [
            {"type": "dataset", "id": d.id, "cells": [f"#{d.id}", d.name, f"#{d.source_id}"], "deleted_at": fmt(d.local_deleted_at)}
            for d in datasets
        ],
        "schema_versions": [
            {"type": "schema_version", "id": sv.id, "cells": [f"#{sv.id}", f"#{sv.dataset_id}", f"v{sv.version_number}"], "deleted_at": fmt(sv.local_deleted_at)}
            for sv in schema_versions
        ],
        "dataset_versions": [
            {"type": "dataset_version", "id": v.id, "cells": [f"#{v.id}", f"#{v.dataset_id}", f"v{v.version_number}"], "deleted_at": fmt(v.local_deleted_at)}
            for v in dataset_versions
        ],
        "feature_sets": [
            {"type": "feature_set", "id": fs.id, "cells": [f"#{fs.id}", fs.name, f"#{fs.dataset_version_id}"], "deleted_at": fmt(fs.local_deleted_at)}
            for fs in feature_sets
        ],
        "experiments": [
            {"type": "experiment", "id": e.id, "cells": [f"#{e.id}", e.name, f"#{e.feature_set_id}"], "deleted_at": fmt(e.local_deleted_at)}
            for e in experiments
        ],
        "models": [
            {"type": "model", "id": m.id, "cells": [f"#{m.id}", m.name, f"#{m.experiment_id}"], "deleted_at": fmt(m.local_deleted_at)}
            for m in models
        ],
    }


@router.get("/search/datasets", response_class=HTMLResponse)
def search_datasets_ui(request: Request, db: DBSession, q: str = "") -> HTMLResponse:
    stmt = select(Dataset).where(Dataset.deleted_at.is_(None))
    if q:
        stmt = stmt.where(Dataset.name.ilike(f"%{q}%"))
    datasets = db.scalars(stmt.order_by(Dataset.id.desc())).all()
    sources = db.scalars(select(DataSource).where(DataSource.deleted_at.is_(None))).all()
    source_lookup = {s.id: s.name for s in sources}
    return templates.TemplateResponse(
        "ui/_datasets_table.html.j2",
        {"request": request, "datasets": datasets, "source_lookup": source_lookup, "filter_q": q},
    )


@router.get("/search/experiments", response_class=HTMLResponse)
def search_experiments_ui(
    request: Request, db: DBSession, q: str = "", status: str = ""
) -> HTMLResponse:
    stmt = select(Experiment).where(Experiment.deleted_at.is_(None))
    if q:
        stmt = stmt.where(Experiment.name.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Experiment.status == status)
    experiments = db.scalars(stmt.order_by(Experiment.id.desc())).all()
    feature_sets = db.scalars(select(FeatureSet).where(FeatureSet.deleted_at.is_(None))).all()
    feature_lookup = {f.id: f.name for f in feature_sets}
    return templates.TemplateResponse(
        "ui/_experiments_table.html.j2",
        {
            "request": request,
            "experiments": experiments,
            "feature_lookup": feature_lookup,
            "filter_q": q,
            "filter_status": status,
        },
    )


@router.get("/archive", response_class=HTMLResponse)
def archive_view(
    request: Request,
    db: DBSession,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        "ui/archive.html.j2",
        {
            "request": request,
            "archived": _archived_rows(db),
            "message": message,
            "error": error,
        },
    )


@router.post("/archive/restore")
def archive_restore(
    db: DBSession,
    entity_type: str = Form(...),
    entity_id: int = Form(...),
) -> RedirectResponse:
    model_cls = _ENTITY_MODELS.get(entity_type)
    if model_cls is None:
        return RedirectResponse(url="/ui/archive", status_code=303)
    obj = db.get(model_cls, entity_id)
    if obj is None or obj.deleted_at is None:
        return RedirectResponse(url="/ui/archive", status_code=303)
    obj.restore()
    db.commit()
    return RedirectResponse(url="/ui/archive", status_code=303)


@router.post("/experiments/{experiment_id}/restore")
def restore_experiment_ui(db: DBSession, experiment_id: int) -> RedirectResponse:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return RedirectResponse(url="/ui", status_code=303)
    if experiment.deleted_at is not None:
        experiment.restore()
        db.commit()
    return RedirectResponse(url=f"/ui/experiments/{experiment_id}", status_code=303)
