import json
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.audit_log import AuditLog
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.datasource import DataSource
from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.models.lineage import LineageEdge
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

LINEAGE_MODES = ["full", "direct", "upstream", "downstream"]

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


def _json_items(payload: dict[str, Any], preferred_key: str) -> dict[str, Any]:
    raw_items = payload.get(preferred_key, [])
    result: dict[str, Any] = {}

    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                name = item.get("name")
                if name is not None:
                    result[str(name)] = item
            else:
                result[str(item)] = item
    elif isinstance(raw_items, dict):
        result = {str(key): value for key, value in raw_items.items()}

    return result


def _compare_json_items(left: dict[str, Any], right: dict[str, Any], preferred_key: str) -> dict[str, list[dict[str, Any]]]:
    left_items = _json_items(left, preferred_key)
    right_items = _json_items(right, preferred_key)
    left_names = set(left_items)
    right_names = set(right_items)

    added = sorted(right_names - left_names)
    removed = sorted(left_names - right_names)
    common = sorted(left_names & right_names)
    changed = [name for name in common if left_items[name] != right_items[name]]
    unchanged = [name for name in common if left_items[name] == right_items[name]]

    return {
        "added": [{"name": name, "right": right_items[name]} for name in added],
        "removed": [{"name": name, "left": left_items[name]} for name in removed],
        "changed": [{"name": name, "left": left_items[name], "right": right_items[name]} for name in changed],
        "unchanged": [{"name": name, "left": left_items[name]} for name in unchanged],
    }


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
            schema_version.id: (
                f"#{schema_version.id} · "
                f"{next((dataset.name for dataset in datasets if dataset.id == schema_version.dataset_id), 'Unknown')} · "
                f"schema v{schema_version.version_number}"
            )
            for schema_version in schema_versions
        },
        "dataset_version_lookup": {
            version.id: (
                f"#{version.id} · "
                f"{next((dataset.name for dataset in datasets if dataset.id == version.dataset_id), 'Unknown')} · "
                f"dataset v{version.version_number}"
            )
            for version in dataset_versions
        },
        "feature_lookup": {feature_set.id: feature_set.name for feature_set in feature_sets},
        "experiment_lookup": {experiment.id: experiment.name for experiment in experiments},
        "model_lookup": {model.id: model.name for model in models},
        "lineage_entity_types": LINEAGE_ENTITY_TYPES,
        "lineage_modes": LINEAGE_MODES,
        "source_type_options": SOURCE_TYPE_OPTIONS,
    }


def _build_report_overviews(data: dict[str, Any]) -> dict[str, dict[int, dict[str, Any]]]:
    sources = {source.id: source for source in data["sources"]}
    datasets = {dataset.id: dataset for dataset in data["datasets"]}
    schema_versions = data["schema_versions"]
    dataset_versions = data["dataset_versions"]
    feature_sets = data["feature_sets"]
    experiments = data["experiments"]
    models = data["models"]

    versions_by_dataset: dict[int, list[DatasetVersion]] = {}
    schemas_by_dataset: dict[int, list[SchemaVersion]] = {}
    models_by_experiment: dict[int, list[Model]] = {}

    for version in dataset_versions:
        versions_by_dataset.setdefault(version.dataset_id, []).append(version)
    for schema_version in schema_versions:
        schemas_by_dataset.setdefault(schema_version.dataset_id, []).append(schema_version)
    for model in models:
        models_by_experiment.setdefault(model.experiment_id, []).append(model)

    dataset_reports: dict[int, dict[str, Any]] = {}
    for dataset in data["datasets"]:
        versions = versions_by_dataset.get(dataset.id, [])
        version_ids = {version.id for version in versions}
        related_features = [feature for feature in feature_sets if feature.dataset_version_id in version_ids]
        source = sources.get(dataset.source_id)
        dataset_reports[dataset.id] = {
            "summary": (
                f"Source: {source.name if source else 'not linked'}; "
                f"schema versions: {len(schemas_by_dataset.get(dataset.id, []))}; "
                f"dataset versions: {len(versions)}; "
                f"feature sets: {len(related_features)}"
            ),
            "includes": [
                "Dataset metadata",
                "Source metadata",
                "Schema versions",
                "Dataset versions",
                "Linked feature sets",
            ],
            "detail_url": f"/ui/datasets/{dataset.id}",
        }

    feature_by_id = {feature.id: feature for feature in feature_sets}
    version_by_id = {version.id: version for version in dataset_versions}

    experiment_reports: dict[int, dict[str, Any]] = {}
    for experiment in experiments:
        feature_set = feature_by_id.get(experiment.feature_set_id)
        dataset_version = version_by_id.get(feature_set.dataset_version_id) if feature_set else None
        dataset = datasets.get(dataset_version.dataset_id) if dataset_version else None
        experiment_reports[experiment.id] = {
            "summary": (
                f"Status: {experiment.status}; "
                f"feature set: {feature_set.name if feature_set else 'not linked'}; "
                f"dataset: {dataset.name if dataset else 'not linked'}; "
                f"models: {len(models_by_experiment.get(experiment.id, []))}"
            ),
            "includes": [
                "Experiment status",
                "Input feature set",
                "Parameters JSON",
                "Metrics table",
                "Produced models",
            ],
            "detail_url": f"/ui/experiments/{experiment.id}",
        }

    experiment_by_id = {experiment.id: experiment for experiment in experiments}

    model_reports: dict[int, dict[str, Any]] = {}
    for model in models:
        experiment = experiment_by_id.get(model.experiment_id)
        feature_set = feature_by_id.get(experiment.feature_set_id) if experiment else None
        dataset_version = version_by_id.get(feature_set.dataset_version_id) if feature_set else None
        dataset = datasets.get(dataset_version.dataset_id) if dataset_version else None
        source = sources.get(dataset.source_id) if dataset else None
        model_reports[model.id] = {
            "summary": (
                f"Framework: {model.framework or 'not set'}; "
                f"experiment: {experiment.name if experiment else 'not linked'}; "
                f"dataset: {dataset.name if dataset else 'not linked'}; "
                f"source: {source.name if source else 'not linked'}"
            ),
            "includes": [
                "Source to model pipeline chain",
                "Dataset and schema versions",
                "Feature schema",
                "Experiment parameters",
                "Metrics and model artifact",
            ],
            "detail_url": f"/ui/models/{model.id}",
        }

    return {
        "datasets": dataset_reports,
        "experiments": experiment_reports,
        "models": model_reports,
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
    selected_lineage_mode: str = "full",
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
        "selected_lineage_mode": selected_lineage_mode,
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
    lineage_mode: str = "full",
) -> HTMLResponse:
    if lineage_mode not in LINEAGE_MODES:
        lineage_mode = "full"

    if entity_type not in LINEAGE_ENTITY_TYPES:
        return _render_dashboard(
            request,
            db,
            lineage_error="Unsupported entity type for lineage lookup",
            selected_entity_type=entity_type,
            selected_entity_id=entity_id,
            selected_lineage_mode=lineage_mode,
            partial="lineage",
        )

    nodes, edges = LineageService.get_graph(db=db, entity_type=entity_type, entity_id=entity_id, mode=lineage_mode)
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
        selected_lineage_mode=lineage_mode,
        partial="lineage",
    )


def _build_lineage_graph(db: DBSession, entity_type: str, entity_id: int, mode: str = "full") -> LineageGraph:
    nodes, edges = LineageService.get_graph(db=db, entity_type=entity_type, entity_id=entity_id, mode=mode)
    return LineageGraph(
        root_entity_type=entity_type,
        root_entity_id=entity_id,
        nodes=[LineageNode(entity_type=node_type, entity_id=node_id) for node_type, node_id in nodes],
        edges=[LineageRead.model_validate(edge) for edge in edges],
    )


def _dependency_item(kind: str, title: str, meta: str, url: str) -> dict[str, str]:
    return {"kind": kind, "title": title, "meta": meta, "url": url}


def _dependency_error_url(path: str, message: str) -> str:
    return f"{path}?error={message.replace(' ', '+')}"


def _entity_detail_url(entity_type: str, entity_id: int) -> str:
    routes = {
        "dataset": "/ui/datasets/{id}",
        "schema_version": "/ui/schema-versions/{id}",
        "dataset_version": "/ui/dataset-versions/{id}",
        "feature_set": "/ui/feature-sets/{id}",
        "experiment": "/ui/experiments/{id}",
        "model": "/ui/models/{id}",
    }
    route = routes.get(entity_type)
    return route.format(id=entity_id) if route else ""


def _search_item(kind: str, title: str, meta: str, url: str) -> dict[str, str]:
    return {"kind": kind, "title": title, "meta": meta, "url": url}


def _build_global_search_results(db: DBSession, query: str) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        return []

    like_query = f"%{query}%"
    results: list[dict[str, str]] = []

    datasets = db.scalars(
        select(Dataset)
        .where(Dataset.deleted_at.is_(None), Dataset.name.ilike(like_query))
        .order_by(Dataset.id.desc())
        .limit(12)
    ).all()
    results.extend(
        _search_item("Dataset", dataset.name, f"#{dataset.id} · source #{dataset.source_id}", f"/ui/datasets/{dataset.id}")
        for dataset in datasets
    )

    feature_sets = db.scalars(
        select(FeatureSet)
        .where(FeatureSet.deleted_at.is_(None), FeatureSet.name.ilike(like_query))
        .order_by(FeatureSet.id.desc())
        .limit(12)
    ).all()
    results.extend(
        _search_item("Feature Set", feature_set.name, f"#{feature_set.id} · data version #{feature_set.dataset_version_id}", f"/ui/feature-sets/{feature_set.id}")
        for feature_set in feature_sets
    )

    experiments = db.scalars(
        select(Experiment)
        .where(Experiment.deleted_at.is_(None), Experiment.name.ilike(like_query))
        .order_by(Experiment.id.desc())
        .limit(12)
    ).all()
    results.extend(
        _search_item("Experiment", experiment.name, f"#{experiment.id} · {experiment.status}", f"/ui/experiments/{experiment.id}")
        for experiment in experiments
    )

    models = db.scalars(
        select(Model)
        .where(Model.deleted_at.is_(None), Model.name.ilike(like_query))
        .order_by(Model.id.desc())
        .limit(12)
    ).all()
    results.extend(
        _search_item("Model", model.name, f"#{model.id} · {model.framework or 'framework not set'}", f"/ui/models/{model.id}")
        for model in models
    )

    if query.isdigit():
        entity_id = int(query)
        schema_version = db.get(SchemaVersion, entity_id)
        if schema_version is not None and schema_version.deleted_at is None:
            results.append(
                _search_item("Schema Version", f"schema v{schema_version.version_number}", f"#{schema_version.id} · dataset #{schema_version.dataset_id}", f"/ui/schema-versions/{schema_version.id}")
            )

        dataset_version = db.get(DatasetVersion, entity_id)
        if dataset_version is not None and dataset_version.deleted_at is None:
            results.append(
                _search_item("Dataset Version", f"data v{dataset_version.version_number}", f"#{dataset_version.id} · dataset #{dataset_version.dataset_id}", f"/ui/dataset-versions/{dataset_version.id}")
            )

    return results


def _entity_display_item(
    db: DBSession,
    entity_type: str,
    entity_id: int,
    relation_type: str,
) -> dict[str, str]:
    title = f"{entity_type.replace('_', ' ')} #{entity_id}"
    meta = f"#{entity_id}"

    if entity_type == "source":
        obj = db.get(DataSource, entity_id)
        if obj is not None:
            title = obj.name
            meta = f"#{obj.id} · {obj.source_type}"
    elif entity_type == "dataset":
        obj = db.get(Dataset, entity_id)
        if obj is not None:
            title = obj.name
            meta = f"#{obj.id}"
    elif entity_type == "schema_version":
        obj = db.get(SchemaVersion, entity_id)
        if obj is not None:
            title = f"schema v{obj.version_number}"
            meta = f"#{obj.id} · dataset #{obj.dataset_id}"
    elif entity_type == "dataset_version":
        obj = db.get(DatasetVersion, entity_id)
        if obj is not None:
            title = f"data v{obj.version_number}"
            meta = f"#{obj.id} · dataset #{obj.dataset_id}"
    elif entity_type == "feature_set":
        obj = db.get(FeatureSet, entity_id)
        if obj is not None:
            title = obj.name
            meta = f"#{obj.id} · data version #{obj.dataset_version_id}"
    elif entity_type == "experiment":
        obj = db.get(Experiment, entity_id)
        if obj is not None:
            title = obj.name
            meta = f"#{obj.id} · {obj.status}"
    elif entity_type == "model":
        obj = db.get(Model, entity_id)
        if obj is not None:
            title = obj.name
            meta = f"#{obj.id} · {obj.framework or 'framework not set'}"

    return {
        "kind": entity_type.replace("_", " ").title(),
        "title": title,
        "meta": meta,
        "relation": relation_type,
        "url": _entity_detail_url(entity_type, entity_id),
    }


def _direct_lineage_dependencies(
    db: DBSession,
    entity_type: str,
    entity_id: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    upstream_edges = LineageService.filter_all(
        db=db,
        where_clause=[
            LineageEdge.to_entity_type == entity_type,
            LineageEdge.to_entity_id == entity_id,
        ],
    )
    downstream_edges = LineageService.filter_all(
        db=db,
        where_clause=[
            LineageEdge.from_entity_type == entity_type,
            LineageEdge.from_entity_id == entity_id,
        ],
    )

    upstream = [
        _entity_display_item(db, edge.from_entity_type, edge.from_entity_id, edge.relation_type)
        for edge in upstream_edges
    ]
    downstream = [
        _entity_display_item(db, edge.to_entity_type, edge.to_entity_id, edge.relation_type)
        for edge in downstream_edges
    ]
    return upstream, downstream


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
    archive_dependencies = [
        _dependency_item("Schema Version", f"schema v{sv.version_number}", f"#{sv.id}", f"/ui/schema-versions/{sv.id}")
        for sv in schema_versions
        if sv.deleted_at is None
    ]
    archive_dependencies.extend(
        _dependency_item("Dataset Version", f"data v{v.version_number}", f"#{v.id}", f"/ui/dataset-versions/{v.id}")
        for v in dataset_versions
        if v.deleted_at is None
    )
    archive_dependencies.extend(
        _dependency_item("Feature Set", fs.name, f"#{fs.id}", f"/ui/feature-sets/{fs.id}")
        for fs in feature_sets
        if fs.deleted_at is None
    )
    source = db.get(DataSource, dataset.source_id)
    lineage_graph = _build_lineage_graph(db, "dataset", dataset_id)
    lineage_upstream, lineage_downstream = _direct_lineage_dependencies(db, "dataset", dataset_id)

    context = {
        **_load_dashboard_data(db),
        "request": request,
        "dataset": dataset,
        "source": source,
        "schema_versions": schema_versions,
        "dataset_versions": dataset_versions,
        "feature_sets": feature_sets,
        "archive_dependencies": archive_dependencies,
        "lineage_upstream": lineage_upstream,
        "lineage_downstream": lineage_downstream,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": None,
        "selected_entity_type": "dataset",
        "selected_entity_id": dataset_id,
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

    has_schema = db.scalar(
        select(SchemaVersion.id)
        .where(SchemaVersion.dataset_id == dataset_id, SchemaVersion.deleted_at.is_(None))
        .limit(1)
    )
    has_version = db.scalar(
        select(DatasetVersion.id)
        .where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.deleted_at.is_(None))
        .limit(1)
    )
    if has_schema is not None or has_version is not None:
        return RedirectResponse(
            url=_dependency_error_url(f"/ui/datasets/{dataset_id}", "Cannot archive dataset: active versions reference it"),
            status_code=303,
        )

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


@router.get("/schema-versions/{schema_version_id}", response_class=HTMLResponse)
def schema_version_detail(
    request: Request,
    db: DBSession,
    schema_version_id: int,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    schema_version = db.get(SchemaVersion, schema_version_id)
    if schema_version is None:
        return _render_dashboard(
            request, db, error=f"Schema version #{schema_version_id} not found", partial="full"
        )

    dataset = db.get(Dataset, schema_version.dataset_id)
    dataset_versions = db.scalars(
        select(DatasetVersion)
        .where(DatasetVersion.schema_version_id == schema_version_id)
        .order_by(DatasetVersion.version_number.desc())
    ).all()
    archive_dependencies = [
        _dependency_item("Dataset Version", f"data v{version.version_number}", f"#{version.id}", f"/ui/dataset-versions/{version.id}")
        for version in dataset_versions
        if version.deleted_at is None
    ]
    lineage_graph = _build_lineage_graph(db, "schema_version", schema_version_id)
    lineage_upstream, lineage_downstream = _direct_lineage_dependencies(db, "schema_version", schema_version_id)

    context = {
        **_load_dashboard_data(db),
        "request": request,
        "schema_version": schema_version,
        "dataset": dataset,
        "dataset_versions": dataset_versions,
        "archive_dependencies": archive_dependencies,
        "lineage_upstream": lineage_upstream,
        "lineage_downstream": lineage_downstream,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": None,
        "selected_entity_type": "schema_version",
        "selected_entity_id": schema_version_id,
    }
    return templates.TemplateResponse("ui/schema_version_detail.html.j2", context)


@router.get("/dataset-versions/{dataset_version_id}", response_class=HTMLResponse)
def dataset_version_detail(
    request: Request,
    db: DBSession,
    dataset_version_id: int,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    dataset_version = db.get(DatasetVersion, dataset_version_id)
    if dataset_version is None:
        return _render_dashboard(
            request, db, error=f"Dataset version #{dataset_version_id} not found", partial="full"
        )

    dataset = db.get(Dataset, dataset_version.dataset_id)
    schema_version = (
        db.get(SchemaVersion, dataset_version.schema_version_id)
        if dataset_version.schema_version_id
        else None
    )
    feature_sets = db.scalars(
        select(FeatureSet)
        .where(FeatureSet.dataset_version_id == dataset_version_id)
        .order_by(FeatureSet.id.desc())
    ).all()
    schema_versions = []
    if dataset is not None:
        schema_versions = db.scalars(
            select(SchemaVersion)
            .where(SchemaVersion.dataset_id == dataset.id, SchemaVersion.deleted_at.is_(None))
            .order_by(SchemaVersion.version_number.desc())
        ).all()
    archive_dependencies = [
        _dependency_item("Feature Set", feature_set.name, f"#{feature_set.id}", f"/ui/feature-sets/{feature_set.id}")
        for feature_set in feature_sets
        if feature_set.deleted_at is None
    ]
    lineage_graph = _build_lineage_graph(db, "dataset_version", dataset_version_id)
    lineage_upstream, lineage_downstream = _direct_lineage_dependencies(db, "dataset_version", dataset_version_id)

    context = {
        **_load_dashboard_data(db),
        "request": request,
        "dataset_version": dataset_version,
        "dataset": dataset,
        "schema_version": schema_version,
        "schema_versions": schema_versions,
        "feature_sets": feature_sets,
        "archive_dependencies": archive_dependencies,
        "lineage_upstream": lineage_upstream,
        "lineage_downstream": lineage_downstream,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": None,
        "selected_entity_type": "dataset_version",
        "selected_entity_id": dataset_version_id,
    }
    return templates.TemplateResponse("ui/dataset_version_detail.html.j2", context)


@router.get("/feature-sets/{feature_set_id}", response_class=HTMLResponse)
def feature_set_detail(
    request: Request,
    db: DBSession,
    feature_set_id: int,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    feature_set = db.get(FeatureSet, feature_set_id)
    if feature_set is None:
        return _render_dashboard(
            request, db, error=f"Feature set #{feature_set_id} not found", partial="full"
        )

    dataset_version = db.get(DatasetVersion, feature_set.dataset_version_id)
    dataset = db.get(Dataset, dataset_version.dataset_id) if dataset_version else None
    experiments = db.scalars(
        select(Experiment)
        .where(Experiment.feature_set_id == feature_set_id)
        .order_by(Experiment.id.desc())
    ).all()
    dataset_versions = db.scalars(
        select(DatasetVersion).where(DatasetVersion.deleted_at.is_(None)).order_by(DatasetVersion.id.desc())
    ).all()
    archive_dependencies = [
        _dependency_item("Experiment", experiment.name, f"#{experiment.id} · {experiment.status}", f"/ui/experiments/{experiment.id}")
        for experiment in experiments
        if experiment.deleted_at is None
    ]
    lineage_graph = _build_lineage_graph(db, "feature_set", feature_set_id)
    lineage_upstream, lineage_downstream = _direct_lineage_dependencies(db, "feature_set", feature_set_id)

    context = {
        **_load_dashboard_data(db),
        "request": request,
        "feature_set": feature_set,
        "dataset_version": dataset_version,
        "dataset": dataset,
        "dataset_versions": dataset_versions,
        "experiments": experiments,
        "archive_dependencies": archive_dependencies,
        "lineage_upstream": lineage_upstream,
        "lineage_downstream": lineage_downstream,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": None,
        "selected_entity_type": "feature_set",
        "selected_entity_id": feature_set_id,
    }
    return templates.TemplateResponse("ui/feature_set_detail.html.j2", context)


@router.get("/models/{model_id}", response_class=HTMLResponse)
def model_detail(
    request: Request,
    db: DBSession,
    model_id: int,
    message: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    model = db.get(Model, model_id)
    if model is None:
        return _render_dashboard(
            request, db, error=f"Model #{model_id} not found", partial="full"
        )

    experiment = db.get(Experiment, model.experiment_id)
    feature_set = db.get(FeatureSet, experiment.feature_set_id) if experiment else None
    dataset_version = db.get(DatasetVersion, feature_set.dataset_version_id) if feature_set else None
    dataset = db.get(Dataset, dataset_version.dataset_id) if dataset_version else None
    lineage_graph = _build_lineage_graph(db, "model", model_id)
    lineage_upstream, lineage_downstream = _direct_lineage_dependencies(db, "model", model_id)

    context = {
        **_load_dashboard_data(db),
        "request": request,
        "model": model,
        "experiment": experiment,
        "feature_set": feature_set,
        "dataset_version": dataset_version,
        "dataset": dataset,
        "archive_dependencies": [],
        "lineage_upstream": lineage_upstream,
        "lineage_downstream": lineage_downstream,
        "message": message,
        "error": error,
        "lineage_graph": lineage_graph,
        "lineage_error": None,
        "selected_entity_type": "model",
        "selected_entity_id": model_id,
    }
    return templates.TemplateResponse("ui/model_detail.html.j2", context)


def _replace_lineage_link(
    db: DBSession,
    *,
    to_entity_type: str,
    to_entity_id: int,
    relation_type: str,
    new_from_entity_type: str | None,
    new_from_entity_id: int | None,
) -> None:
    edges = LineageService.filter_all(
        db=db,
        where_clause=[
            LineageEdge.to_entity_type == to_entity_type,
            LineageEdge.to_entity_id == to_entity_id,
            LineageEdge.relation_type == relation_type,
        ],
    )
    for edge in edges:
        edge.mark_deleted()

    if new_from_entity_type is not None and new_from_entity_id is not None:
        LineageService.create(
            db=db,
            from_entity_type=new_from_entity_type,
            from_entity_id=new_from_entity_id,
            to_entity_type=to_entity_type,
            to_entity_id=to_entity_id,
            relation_type=relation_type,
        )


@router.post("/models/{model_id}/update")
def update_model_ui(
    db: DBSession,
    model_id: int,
    name: str = Form(...),
    experiment_id: int = Form(...),
    framework: str = Form(""),
    version: str = Form(""),
    artifact_path: str = Form(""),
    description: str = Form(""),
) -> RedirectResponse:
    model = db.get(Model, model_id)
    if model is None:
        return RedirectResponse(url="/ui", status_code=303)
    if model.deleted_at is not None:
        return RedirectResponse(
            url=f"/ui/models/{model_id}?error=Archived+model+cannot+be+edited",
            status_code=303,
        )

    experiment = db.get(Experiment, experiment_id)
    if experiment is None or experiment.deleted_at is not None:
        return RedirectResponse(
            url=f"/ui/models/{model_id}?error=Experiment+does+not+exist",
            status_code=303,
        )

    try:
        model.name = name.strip()
        model.experiment_id = experiment_id
        model.framework = framework.strip() or None
        model.version = version.strip() or None
        model.artifact_path = artifact_path.strip() or None
        model.description = description.strip() or None
        _replace_lineage_link(
            db,
            to_entity_type="model",
            to_entity_id=model.id,
            relation_type="produces_model",
            new_from_entity_type="experiment",
            new_from_entity_id=experiment_id,
        )
        _commit_or_rollback(db)
        return RedirectResponse(
            url=f"/ui/models/{model_id}?message=Model+updated",
            status_code=303,
        )
    except (ValueError, IntegrityError):
        db.rollback()
        return RedirectResponse(
            url=f"/ui/models/{model_id}?error=Model+was+not+updated",
            status_code=303,
        )


@router.post("/models/{model_id}/delete")
def delete_model_ui(db: DBSession, model_id: int) -> RedirectResponse:
    model = db.get(Model, model_id)
    if model is None:
        return RedirectResponse(url="/ui", status_code=303)
    if model.deleted_at is None:
        model.mark_deleted()
        db.commit()
    return RedirectResponse(url=f"/ui/models/{model_id}", status_code=303)


@router.post("/models/{model_id}/restore")
def restore_model_ui(db: DBSession, model_id: int) -> RedirectResponse:
    model = db.get(Model, model_id)
    if model is None:
        return RedirectResponse(url="/ui", status_code=303)
    if model.deleted_at is not None:
        model.restore()
        db.commit()
    return RedirectResponse(url=f"/ui/models/{model_id}", status_code=303)


@router.post("/schema-versions/{schema_version_id}/delete")
def delete_schema_version_ui(db: DBSession, schema_version_id: int) -> RedirectResponse:
    schema_version = db.get(SchemaVersion, schema_version_id)
    if schema_version is None:
        return RedirectResponse(url="/ui", status_code=303)

    has_active_dataset_version = db.scalar(
        select(DatasetVersion.id)
        .where(
            DatasetVersion.schema_version_id == schema_version_id,
            DatasetVersion.deleted_at.is_(None),
        )
        .limit(1)
    )
    if has_active_dataset_version is not None:
        return RedirectResponse(
            url=f"/ui/schema-versions/{schema_version_id}?error=Cannot+archive+schema+version:+active+dataset+versions+reference+it",
            status_code=303,
        )

    if schema_version.deleted_at is None:
        schema_version.mark_deleted()
        db.commit()
    return RedirectResponse(url=f"/ui/schema-versions/{schema_version_id}", status_code=303)


@router.post("/schema-versions/{schema_version_id}/restore")
def restore_schema_version_ui(db: DBSession, schema_version_id: int) -> RedirectResponse:
    schema_version = db.get(SchemaVersion, schema_version_id)
    if schema_version is None:
        return RedirectResponse(url="/ui", status_code=303)
    if schema_version.deleted_at is not None:
        schema_version.restore()
        db.commit()
    return RedirectResponse(url=f"/ui/schema-versions/{schema_version_id}", status_code=303)


@router.post("/dataset-versions/{dataset_version_id}/delete")
def delete_dataset_version_ui(db: DBSession, dataset_version_id: int) -> RedirectResponse:
    dataset_version = db.get(DatasetVersion, dataset_version_id)
    if dataset_version is None:
        return RedirectResponse(url="/ui", status_code=303)

    has_active_feature_set = db.scalar(
        select(FeatureSet.id)
        .where(
            FeatureSet.dataset_version_id == dataset_version_id,
            FeatureSet.deleted_at.is_(None),
        )
        .limit(1)
    )
    if has_active_feature_set is not None:
        return RedirectResponse(
            url=f"/ui/dataset-versions/{dataset_version_id}?error=Cannot+archive+dataset+version:+active+feature+sets+reference+it",
            status_code=303,
        )

    if dataset_version.deleted_at is None:
        dataset_version.mark_deleted()
        db.commit()
    return RedirectResponse(url=f"/ui/dataset-versions/{dataset_version_id}", status_code=303)


@router.post("/dataset-versions/{dataset_version_id}/restore")
def restore_dataset_version_ui(db: DBSession, dataset_version_id: int) -> RedirectResponse:
    dataset_version = db.get(DatasetVersion, dataset_version_id)
    if dataset_version is None:
        return RedirectResponse(url="/ui", status_code=303)
    if dataset_version.deleted_at is not None:
        dataset_version.restore()
        db.commit()
    return RedirectResponse(url=f"/ui/dataset-versions/{dataset_version_id}", status_code=303)


@router.post("/feature-sets/{feature_set_id}/delete")
def delete_feature_set_ui(db: DBSession, feature_set_id: int) -> RedirectResponse:
    feature_set = db.get(FeatureSet, feature_set_id)
    if feature_set is None:
        return RedirectResponse(url="/ui", status_code=303)

    has_active_experiment = db.scalar(
        select(Experiment.id)
        .where(
            Experiment.feature_set_id == feature_set_id,
            Experiment.deleted_at.is_(None),
        )
        .limit(1)
    )
    if has_active_experiment is not None:
        return RedirectResponse(
            url=f"/ui/feature-sets/{feature_set_id}?error=Cannot+archive+feature+set:+active+experiments+reference+it",
            status_code=303,
        )

    if feature_set.deleted_at is None:
        feature_set.mark_deleted()
        db.commit()
    return RedirectResponse(url=f"/ui/feature-sets/{feature_set_id}", status_code=303)


@router.post("/feature-sets/{feature_set_id}/restore")
def restore_feature_set_ui(db: DBSession, feature_set_id: int) -> RedirectResponse:
    feature_set = db.get(FeatureSet, feature_set_id)
    if feature_set is None:
        return RedirectResponse(url="/ui", status_code=303)
    if feature_set.deleted_at is not None:
        feature_set.restore()
        db.commit()
    return RedirectResponse(url=f"/ui/feature-sets/{feature_set_id}", status_code=303)


@router.post("/schema-versions/{schema_version_id}/update")
def update_schema_version_ui(
    db: DBSession,
    schema_version_id: int,
    dataset_id: int = Form(...),
    version_number: str = Form(...),
    schema_json: str = Form(...),
) -> RedirectResponse:
    schema_version = db.get(SchemaVersion, schema_version_id)
    if schema_version is None:
        return RedirectResponse(url="/ui", status_code=303)
    if schema_version.deleted_at is not None:
        return RedirectResponse(
            url=f"/ui/schema-versions/{schema_version_id}?error=Archived+schema+version+cannot+be+edited",
            status_code=303,
        )

    try:
        dataset = db.get(Dataset, dataset_id)
        if dataset is None or dataset.deleted_at is not None:
            raise ValueError("Selected dataset does not exist")

        linked_dataset_versions = db.scalars(
            select(DatasetVersion).where(DatasetVersion.schema_version_id == schema_version_id)
        ).all()
        if dataset_id != schema_version.dataset_id and linked_dataset_versions:
            raise ValueError("Schema version is already used by dataset versions")

        parsed_version = _parse_optional_int(version_number)
        if parsed_version is None:
            raise ValueError("Version number is required")
        schema_version.dataset_id = dataset_id
        schema_version.version_number = parsed_version
        schema_version.schema_json = _parse_json_field(schema_json, "schema_json")
        _replace_lineage_link(
            db,
            to_entity_type="schema_version",
            to_entity_id=schema_version.id,
            relation_type="has_schema_version",
            new_from_entity_type="dataset",
            new_from_entity_id=dataset_id,
        )
        _commit_or_rollback(db)
        return RedirectResponse(
            url=f"/ui/schema-versions/{schema_version_id}?message=Schema+version+updated",
            status_code=303,
        )
    except (ValueError, IntegrityError):
        db.rollback()
        return RedirectResponse(
            url=f"/ui/schema-versions/{schema_version_id}?error=Schema+version+was+not+updated",
            status_code=303,
        )


@router.post("/dataset-versions/{dataset_version_id}/update")
def update_dataset_version_ui(
    db: DBSession,
    dataset_version_id: int,
    version_number: str = Form(...),
    schema_version_id: str = Form(""),
) -> RedirectResponse:
    dataset_version = db.get(DatasetVersion, dataset_version_id)
    if dataset_version is None:
        return RedirectResponse(url="/ui", status_code=303)
    if dataset_version.deleted_at is not None:
        return RedirectResponse(
            url=f"/ui/dataset-versions/{dataset_version_id}?error=Archived+dataset+version+cannot+be+edited",
            status_code=303,
        )

    try:
        parsed_version = _parse_optional_int(version_number)
        if parsed_version is None:
            raise ValueError("Version number is required")
        schema_id = _parse_optional_int(schema_version_id)
        if schema_id is not None:
            schema_version = db.get(SchemaVersion, schema_id)
            if schema_version is None or schema_version.deleted_at is not None:
                raise ValueError("Selected schema version does not exist")
            if schema_version.dataset_id != dataset_version.dataset_id:
                raise ValueError("Schema version belongs to another dataset")

        dataset_version.version_number = parsed_version
        dataset_version.schema_version_id = schema_id
        _replace_lineage_link(
            db,
            to_entity_type="dataset_version",
            to_entity_id=dataset_version.id,
            relation_type="defines_schema_for",
            new_from_entity_type="schema_version" if schema_id is not None else None,
            new_from_entity_id=schema_id,
        )
        _commit_or_rollback(db)
        return RedirectResponse(
            url=f"/ui/dataset-versions/{dataset_version_id}?message=Dataset+version+updated",
            status_code=303,
        )
    except (ValueError, IntegrityError):
        db.rollback()
        return RedirectResponse(
            url=f"/ui/dataset-versions/{dataset_version_id}?error=Dataset+version+was+not+updated",
            status_code=303,
        )


@router.post("/feature-sets/{feature_set_id}/update")
def update_feature_set_ui(
    db: DBSession,
    feature_set_id: int,
    name: str = Form(...),
    dataset_version_id: int = Form(...),
    feature_schema_json: str = Form(...),
) -> RedirectResponse:
    feature_set = db.get(FeatureSet, feature_set_id)
    if feature_set is None:
        return RedirectResponse(url="/ui", status_code=303)
    if feature_set.deleted_at is not None:
        return RedirectResponse(
            url=f"/ui/feature-sets/{feature_set_id}?error=Archived+feature+set+cannot+be+edited",
            status_code=303,
        )

    dataset_version = db.get(DatasetVersion, dataset_version_id)
    if dataset_version is None or dataset_version.deleted_at is not None:
        return RedirectResponse(
            url=f"/ui/feature-sets/{feature_set_id}?error=Dataset+version+does+not+exist",
            status_code=303,
        )

    try:
        feature_set.name = name.strip()
        feature_set.dataset_version_id = dataset_version_id
        feature_set.feature_schema_json = _parse_json_field(feature_schema_json, "feature_schema_json")
        _replace_lineage_link(
            db,
            to_entity_type="feature_set",
            to_entity_id=feature_set.id,
            relation_type="produces_features",
            new_from_entity_type="dataset_version",
            new_from_entity_id=dataset_version_id,
        )
        _commit_or_rollback(db)
        return RedirectResponse(
            url=f"/ui/feature-sets/{feature_set_id}?message=Feature+set+updated",
            status_code=303,
        )
    except (ValueError, IntegrityError):
        db.rollback()
        return RedirectResponse(
            url=f"/ui/feature-sets/{feature_set_id}?error=Feature+set+was+not+updated",
            status_code=303,
        )


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
    models = db.scalars(
        select(Model)
        .where(Model.experiment_id == experiment_id)
        .order_by(Model.id.desc())
    ).all()
    archive_dependencies = [
        _dependency_item("Model", model.name, f"#{model.id} · {model.framework or 'framework not set'}", f"/ui/models/{model.id}")
        for model in models
        if model.deleted_at is None
    ]
    lineage_graph = _build_lineage_graph(db, "experiment", experiment_id)
    lineage_upstream, lineage_downstream = _direct_lineage_dependencies(db, "experiment", experiment_id)

    context = {
        "request": request,
        "experiment": experiment,
        "feature_set": feature_set,
        "dataset_version": dataset_version,
        "dataset": dataset,
        "models": models,
        "archive_dependencies": archive_dependencies,
        "lineage_upstream": lineage_upstream,
        "lineage_downstream": lineage_downstream,
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

    has_model = db.scalar(
        select(Model.id)
        .where(Model.experiment_id == experiment_id, Model.deleted_at.is_(None))
        .limit(1)
    )
    if has_model is not None:
        return RedirectResponse(
            url=_dependency_error_url(f"/ui/experiments/{experiment_id}", "Cannot archive experiment: active models reference it"),
            status_code=303,
        )

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


@router.post("/experiments/{experiment_id}/update")
def update_experiment_ui(
    db: DBSession,
    experiment_id: int,
    name: str = Form(...),
    parameters_json: str = Form(...),
    metrics_json: str = Form(...),
    notebook_url: str = Form(""),
    report_path: str = Form(""),
) -> RedirectResponse:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return RedirectResponse(url="/ui", status_code=303)
    if experiment.deleted_at is not None:
        return RedirectResponse(
            url=f"/ui/experiments/{experiment_id}?error=Archived+experiment+cannot+be+edited",
            status_code=303,
        )

    try:
        experiment.name = name.strip()
        experiment.parameters_json = _parse_json_field(parameters_json, "parameters_json")
        experiment.metrics_json = _parse_json_field(metrics_json, "metrics_json")
        experiment.notebook_url = notebook_url.strip() or None
        experiment.report_path = report_path.strip() or None
        _commit_or_rollback(db)
        return RedirectResponse(
            url=f"/ui/experiments/{experiment_id}?message=Experiment+updated",
            status_code=303,
        )
    except (ValueError, IntegrityError):
        db.rollback()
        return RedirectResponse(
            url=f"/ui/experiments/{experiment_id}?error=Experiment+was+not+updated",
            status_code=303,
        )


_ENTITY_MODELS = {
    "source": DataSource,
    "dataset": Dataset,
    "schema_version": SchemaVersion,
    "dataset_version": DatasetVersion,
    "feature_set": FeatureSet,
    "experiment": Experiment,
    "model": Model,
}


def _archived_rows(db: DBSession, entity_type: str = "", q: str = "") -> dict[str, list[dict]]:
    def fmt(dt) -> str:
        return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"

    def linked_id(row_type: str, row_id: int) -> dict[str, str]:
        return {"text": f"#{row_id}", "url": _entity_detail_url(row_type, row_id)}

    def row_matches(row: dict) -> bool:
        if entity_type and row["type"] != entity_type:
            return False
        if not q:
            return True
        haystack = " ".join(str(cell.get("text", "")) if isinstance(cell, dict) else str(cell) for cell in row["cells"])
        haystack = f"{row['type']} {haystack} {row['deleted_at']}".lower()
        return q.lower() in haystack

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

    rows = {
        "sources": [
            {"type": "source", "id": s.id, "cells": [f"#{s.id}", s.name, s.source_type], "deleted_at": fmt(s.local_deleted_at)}
            for s in sources
        ],
        "datasets": [
            {"type": "dataset", "id": d.id, "cells": [linked_id("dataset", d.id), d.name, f"#{d.source_id}"], "deleted_at": fmt(d.local_deleted_at)}
            for d in datasets
        ],
        "schema_versions": [
            {"type": "schema_version", "id": sv.id, "cells": [linked_id("schema_version", sv.id), f"#{sv.dataset_id}", f"v{sv.version_number}"], "deleted_at": fmt(sv.local_deleted_at)}
            for sv in schema_versions
        ],
        "dataset_versions": [
            {"type": "dataset_version", "id": v.id, "cells": [linked_id("dataset_version", v.id), f"#{v.dataset_id}", f"v{v.version_number}"], "deleted_at": fmt(v.local_deleted_at)}
            for v in dataset_versions
        ],
        "feature_sets": [
            {"type": "feature_set", "id": fs.id, "cells": [linked_id("feature_set", fs.id), fs.name, f"#{fs.dataset_version_id}"], "deleted_at": fmt(fs.local_deleted_at)}
            for fs in feature_sets
        ],
        "experiments": [
            {"type": "experiment", "id": e.id, "cells": [linked_id("experiment", e.id), e.name, f"#{e.feature_set_id}"], "deleted_at": fmt(e.local_deleted_at)}
            for e in experiments
        ],
        "models": [
            {"type": "model", "id": m.id, "cells": [linked_id("model", m.id), m.name, f"#{m.experiment_id}"], "deleted_at": fmt(m.local_deleted_at)}
            for m in models
        ],
    }

    return {section: [row for row in section_rows if row_matches(row)] for section, section_rows in rows.items()}


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


@router.get("/reports", response_class=HTMLResponse)
def reports_view(request: Request, db: DBSession) -> HTMLResponse:
    dashboard_data = _load_dashboard_data(db)
    return templates.TemplateResponse(
        "ui/reports.html.j2",
        {
            "request": request,
            "report_overviews": _build_report_overviews(dashboard_data),
            **dashboard_data,
        },
    )


@router.get("/search", response_class=HTMLResponse)
def global_search_view(request: Request, db: DBSession, q: str = "") -> HTMLResponse:
    results = _build_global_search_results(db, q)
    return templates.TemplateResponse(
        "ui/search.html.j2",
        {
            "request": request,
            "q": q,
            "results": results,
        },
    )


@router.get("/compare", response_class=HTMLResponse)
def compare_view(
    request: Request,
    db: DBSession,
    compare_type: str = "schema",
    left_id: int | None = None,
    right_id: int | None = None,
) -> HTMLResponse:
    if compare_type not in {"schema", "feature_set"}:
        compare_type = "schema"

    data = _load_dashboard_data(db)
    result = None
    left_obj = None
    right_obj = None
    error = None

    if left_id is not None and right_id is not None:
        if compare_type == "schema":
            left_obj = db.get(SchemaVersion, left_id)
            right_obj = db.get(SchemaVersion, right_id)
            if left_obj is None or right_obj is None:
                error = "Selected schema version does not exist"
            elif left_obj.dataset_id != right_obj.dataset_id:
                error = "Schema versions must belong to the same dataset"
            else:
                result = _compare_json_items(left_obj.schema_json, right_obj.schema_json, "fields")
        else:
            left_obj = db.get(FeatureSet, left_id)
            right_obj = db.get(FeatureSet, right_id)
            if left_obj is None or right_obj is None:
                error = "Selected feature set does not exist"
            else:
                result = _compare_json_items(left_obj.feature_schema_json, right_obj.feature_schema_json, "features")

    return templates.TemplateResponse(
        "ui/compare.html.j2",
        {
            "request": request,
            "compare_type": compare_type,
            "left_id": left_id,
            "right_id": right_id,
            "left_obj": left_obj,
            "right_obj": right_obj,
            "result": result,
            "error": error,
            **data,
        },
    )


@router.get("/audit", response_class=HTMLResponse)
def audit_view(
    request: Request,
    db: DBSession,
    q: str = "",
    entity_type: str = "",
    action: str = "",
) -> HTMLResponse:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
    if q:
        stmt = stmt.where(AuditLog.entity_name.ilike(f"%{q}%"))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    audit_logs = db.scalars(stmt).all()

    is_partial = request.headers.get("HX-Request") == "true"
    template = "ui/_audit_table.html.j2" if is_partial else "ui/audit.html.j2"
    return templates.TemplateResponse(
        template,
        {
            "request": request,
            "audit_logs": audit_logs,
            "filter_q": q,
            "filter_entity_type": entity_type,
            "filter_action": action,
        },
    )


@router.get("/archive", response_class=HTMLResponse)
def archive_view(
    request: Request,
    db: DBSession,
    message: str | None = None,
    error: str | None = None,
    entity_type: str = "",
    q: str = "",
) -> HTMLResponse:
    return templates.TemplateResponse(
        "ui/archive.html.j2",
        {
            "request": request,
            "archived": _archived_rows(db, entity_type=entity_type, q=q),
            "archive_entity_type": entity_type,
            "archive_q": q,
            "archive_entity_types": list(_ENTITY_MODELS.keys()),
            "message": message,
            "error": error,
        },
    )


@router.post("/archive/restore")
def archive_restore(
    db: DBSession,
    entity_type: str = Form(...),
    entity_id: int = Form(...),
    filter_entity_type: str = Form(""),
    q: str = Form(""),
) -> RedirectResponse:
    params = []
    if filter_entity_type:
        params.append(f"entity_type={filter_entity_type}")
    if q:
        params.append(f"q={q}")
    archive_url = "/ui/archive" + ("?" + "&".join(params) if params else "")

    model_cls = _ENTITY_MODELS.get(entity_type)
    if model_cls is None:
        return RedirectResponse(url=archive_url, status_code=303)
    obj = db.get(model_cls, entity_id)
    if obj is None or obj.deleted_at is None:
        return RedirectResponse(url=archive_url, status_code=303)
    obj.restore()
    db.commit()
    return RedirectResponse(url=archive_url, status_code=303)


@router.post("/experiments/{experiment_id}/restore")
def restore_experiment_ui(db: DBSession, experiment_id: int) -> RedirectResponse:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return RedirectResponse(url="/ui", status_code=303)
    if experiment.deleted_at is not None:
        experiment.restore()
        db.commit()
    return RedirectResponse(url=f"/ui/experiments/{experiment_id}", status_code=303)
