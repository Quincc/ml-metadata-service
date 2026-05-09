import json
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.datasource import DataSource
from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.routers import DBSession
from app.models.schema_version import SchemaVersion
from app.schemas.lineage import LineageGraph, LineageNode, LineageRead
from app.services.lineage_service import LineageService
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
    sources = db.scalars(select(DataSource).order_by(DataSource.id.desc())).all()
    datasets = db.scalars(select(Dataset).order_by(Dataset.id.desc())).all()
    schema_versions = db.scalars(select(SchemaVersion).order_by(SchemaVersion.id.desc())).all()
    dataset_versions = db.scalars(select(DatasetVersion).order_by(DatasetVersion.id.desc())).all()
    feature_sets = db.scalars(select(FeatureSet).order_by(FeatureSet.id.desc())).all()
    experiments = db.scalars(select(Experiment).order_by(Experiment.id.desc())).all()

    return {
        "sources": sources,
        "datasets": datasets,
        "schema_versions": schema_versions,
        "dataset_versions": dataset_versions,
        "feature_sets": feature_sets,
        "experiments": experiments,
        "counts": {
            "sources": len(sources),
            "datasets": len(datasets),
            "schema_versions": len(schema_versions),
            "dataset_versions": len(dataset_versions),
            "feature_sets": len(feature_sets),
            "experiments": len(experiments),
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
    selected_entity_type: str = "dataset",
    selected_entity_id: int | None = None,
    full_page: bool = False,
) -> HTMLResponse:
    context = {
        "request": request,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "selected_entity_type": selected_entity_type,
        "selected_entity_id": selected_entity_id,
        **_load_dashboard_data(db),
    }
    template_name = "ui/index.html.j2" if full_page else "ui/_dashboard_content.html.j2"
    return templates.TemplateResponse(template_name, context)


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
    return _render_dashboard(request, db, full_page=True)


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


@router.get("/lineage", response_class=HTMLResponse)
def view_lineage_ui(
    request: Request,
    db: DBSession,
    entity_type: str,
    entity_id: int,
) -> HTMLResponse:
    if entity_type not in LINEAGE_ENTITY_TYPES:
        return _render_dashboard(request, db, error="Unsupported entity type for lineage lookup")

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
        message=f"Lineage loaded for {entity_type} #{entity_id}",
        lineage_graph=lineage_graph,
        selected_entity_type=entity_type,
        selected_entity_id=entity_id,
    )
