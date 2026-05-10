from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.db import SessionLocal, wait_for_database
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.datasource import DataSource
from app.models.experiment import Experiment
from app.models.feature_set import FeatureSet
from app.models.lineage import LineageEdge
from app.models.model import Model
from app.models.schema_version import SchemaVersion

DEMO_CATALOG = [
    {
        "source": {
            "name": "Titanic Kaggle CSV",
            "source_type": "csv",
            "location": "data/raw/titanic_dataset.csv",
        },
        "dataset": {
            "name": "titanic_survival",
            "description": "Passenger survival prediction dataset with raw and cleaned versions.",
        },
        "schemas": [
            {
                "version_number": 1,
                "schema_json": {
                    "fields": [
                        {"name": "PassengerId", "type": "int"},
                        {"name": "Survived", "type": "int"},
                        {"name": "Pclass", "type": "int"},
                        {"name": "Name", "type": "string"},
                        {"name": "Sex", "type": "string"},
                        {"name": "Age", "type": "float"},
                        {"name": "SibSp", "type": "int"},
                        {"name": "Parch", "type": "int"},
                        {"name": "Ticket", "type": "string"},
                        {"name": "Fare", "type": "float"},
                        {"name": "Cabin", "type": "string"},
                        {"name": "Embarked", "type": "string"},
                    ]
                },
            },
            {
                "version_number": 2,
                "schema_json": {
                    "fields": [
                        {"name": "PassengerId", "type": "int"},
                        {"name": "Survived", "type": "int"},
                        {"name": "Pclass", "type": "int"},
                        {"name": "SexEncoded", "type": "int"},
                        {"name": "Age", "type": "float"},
                        {"name": "SibSp", "type": "int"},
                        {"name": "Parch", "type": "int"},
                        {"name": "Fare", "type": "float"},
                        {"name": "EmbarkedEncoded", "type": "int"},
                        {"name": "FamilySize", "type": "int"},
                    ]
                },
            },
        ],
        "dataset_versions": [
            {"version_number": 1, "schema_version_number": 1},
            {"version_number": 2, "schema_version_number": 2},
        ],
        "feature_sets": [
            {
                "name": "titanic_features_baseline",
                "dataset_version_number": 2,
                "feature_schema_json": {
                    "features": ["Pclass", "SexEncoded", "Age", "Fare"],
                    "target": "Survived",
                },
            },
            {
                "name": "titanic_features_extended",
                "dataset_version_number": 2,
                "feature_schema_json": {
                    "features": [
                        "Pclass",
                        "SexEncoded",
                        "Age",
                        "Fare",
                        "FamilySize",
                        "EmbarkedEncoded",
                    ],
                    "target": "Survived",
                },
            },
        ],
        "experiments": [
            {
                "name": "titanic_logreg_baseline",
                "feature_set_name": "titanic_features_baseline",
                "parameters_json": {
                    "model": "LogisticRegression",
                    "max_iter": 1000,
                    "random_state": 42,
                },
                "metrics_json": {"accuracy": 0.81, "f1": 0.77, "roc_auc": 0.85},
            },
            {
                "name": "titanic_random_forest",
                "feature_set_name": "titanic_features_extended",
                "parameters_json": {
                    "model": "RandomForestClassifier",
                    "n_estimators": 200,
                    "max_depth": 6,
                    "random_state": 42,
                },
                "metrics_json": {"accuracy": 0.84, "f1": 0.8, "roc_auc": 0.88},
            },
            {
                "name": "titanic_xgboost_tuned",
                "feature_set_name": "titanic_features_extended",
                "parameters_json": {
                    "model": "XGBoost",
                    "max_depth": 5,
                    "learning_rate": 0.05,
                    "n_estimators": 300,
                },
                "metrics_json": {"accuracy": 0.86, "f1": 0.82, "roc_auc": 0.9},
            },
        ],
    },
    {
        "source": {
            "name": "CRM Warehouse Postgres",
            "source_type": "postgresql",
            "location": "postgresql://warehouse.local:5432/crm",
        },
        "dataset": {
            "name": "customer_churn",
            "description": "Customer churn dataset with transactional enrichment.",
        },
        "schemas": [
            {
                "version_number": 1,
                "schema_json": {
                    "fields": [
                        {"name": "customer_id", "type": "int"},
                        {"name": "age", "type": "int"},
                        {"name": "balance", "type": "float"},
                        {"name": "tenure", "type": "int"},
                        {"name": "target", "type": "int"},
                    ]
                },
            },
            {
                "version_number": 2,
                "schema_json": {
                    "fields": [
                        {"name": "customer_id", "type": "int"},
                        {"name": "age", "type": "int"},
                        {"name": "balance", "type": "float"},
                        {"name": "tenure", "type": "int"},
                        {"name": "num_products", "type": "int"},
                        {"name": "is_active_member", "type": "int"},
                        {"name": "target", "type": "int"},
                    ]
                },
            },
        ],
        "dataset_versions": [
            {"version_number": 1, "schema_version_number": 1},
            {"version_number": 2, "schema_version_number": 2},
        ],
        "feature_sets": [
            {
                "name": "churn_features_baseline",
                "dataset_version_number": 1,
                "feature_schema_json": {
                    "features": ["age", "balance", "tenure"],
                    "target": "target",
                },
            },
            {
                "name": "churn_features_enriched",
                "dataset_version_number": 2,
                "feature_schema_json": {
                    "features": [
                        "age",
                        "balance",
                        "tenure",
                        "num_products",
                        "is_active_member",
                    ],
                    "target": "target",
                },
            },
        ],
        "experiments": [
            {
                "name": "churn_logreg_baseline",
                "feature_set_name": "churn_features_baseline",
                "parameters_json": {
                    "model": "LogisticRegression",
                    "max_iter": 2000,
                    "class_weight": "balanced",
                },
                "metrics_json": {"accuracy": 0.79, "f1": 0.74, "roc_auc": 0.83},
            },
            {
                "name": "churn_catboost_enriched",
                "feature_set_name": "churn_features_enriched",
                "parameters_json": {
                    "model": "CatBoostClassifier",
                    "depth": 6,
                    "iterations": 400,
                    "learning_rate": 0.05,
                },
                "metrics_json": {"accuracy": 0.85, "f1": 0.81, "roc_auc": 0.89},
            },
        ],
    },
    {
        "source": {
            "name": "House Prices Parquet Lake",
            "source_type": "parquet",
            "location": "s3://demo-lake/house-prices/",
        },
        "dataset": {
            "name": "house_prices_regression",
            "description": "Housing price prediction dataset for regression experiments.",
        },
        "schemas": [
            {
                "version_number": 1,
                "schema_json": {
                    "fields": [
                        {"name": "id", "type": "int"},
                        {"name": "overall_qual", "type": "int"},
                        {"name": "gr_liv_area", "type": "int"},
                        {"name": "garage_cars", "type": "int"},
                        {"name": "year_built", "type": "int"},
                        {"name": "sale_price", "type": "float"},
                    ]
                },
            },
            {
                "version_number": 2,
                "schema_json": {
                    "fields": [
                        {"name": "id", "type": "int"},
                        {"name": "overall_qual", "type": "int"},
                        {"name": "gr_liv_area", "type": "int"},
                        {"name": "garage_cars", "type": "int"},
                        {"name": "year_built", "type": "int"},
                        {"name": "house_age", "type": "int"},
                        {"name": "total_bathrooms", "type": "float"},
                        {"name": "sale_price", "type": "float"},
                    ]
                },
            },
        ],
        "dataset_versions": [
            {"version_number": 1, "schema_version_number": 1},
            {"version_number": 2, "schema_version_number": 2},
        ],
        "feature_sets": [
            {
                "name": "house_prices_linear_features",
                "dataset_version_number": 1,
                "feature_schema_json": {
                    "features": ["overall_qual", "gr_liv_area", "garage_cars", "year_built"],
                    "target": "sale_price",
                },
            },
            {
                "name": "house_prices_engineered_features",
                "dataset_version_number": 2,
                "feature_schema_json": {
                    "features": [
                        "overall_qual",
                        "gr_liv_area",
                        "garage_cars",
                        "year_built",
                        "house_age",
                        "total_bathrooms",
                    ],
                    "target": "sale_price",
                },
            },
        ],
        "experiments": [
            {
                "name": "house_prices_linear_regression",
                "feature_set_name": "house_prices_linear_features",
                "parameters_json": {"model": "LinearRegression", "fit_intercept": True},
                "metrics_json": {"rmse": 31250.4, "mae": 20110.8, "r2": 0.78},
            },
            {
                "name": "house_prices_lightgbm",
                "feature_set_name": "house_prices_engineered_features",
                "parameters_json": {
                    "model": "LightGBMRegressor",
                    "num_leaves": 31,
                    "learning_rate": 0.05,
                    "n_estimators": 500,
                },
                "metrics_json": {"rmse": 24880.7, "mae": 16230.5, "r2": 0.86},
            },
        ],
    },
]


def get_one_or_none(session, model, *where_clauses):
    statement = select(model).where(*where_clauses)
    return session.execute(statement).scalar_one_or_none()


def ensure_lineage_edge(session, **payload):
    edge = get_one_or_none(
        session,
        LineageEdge,
        LineageEdge.from_entity_type == payload["from_entity_type"],
        LineageEdge.from_entity_id == payload["from_entity_id"],
        LineageEdge.to_entity_type == payload["to_entity_type"],
        LineageEdge.to_entity_id == payload["to_entity_id"],
        LineageEdge.relation_type == payload["relation_type"],
        LineageEdge.deleted_at.is_(None),
    )
    if edge is None:
        edge = LineageEdge(**payload)
        session.add(edge)
    return edge


def ensure_source(session, payload):
    source = get_one_or_none(session, DataSource, DataSource.name == payload["name"], DataSource.deleted_at.is_(None))
    if source is None:
        source = DataSource(**payload)
        session.add(source)
        session.flush()
    else:
        source.source_type = payload["source_type"]
        source.location = payload["location"]
    return source


def ensure_dataset(session, source, payload):
    dataset = get_one_or_none(session, Dataset, Dataset.name == payload["name"], Dataset.deleted_at.is_(None))
    if dataset is None:
        dataset = Dataset(source_id=source.id, **payload)
        session.add(dataset)
        session.flush()
    else:
        dataset.source_id = source.id
        dataset.description = payload["description"]
    ensure_lineage_edge(
        session,
        from_entity_type="source",
        from_entity_id=source.id,
        to_entity_type="dataset",
        to_entity_id=dataset.id,
        relation_type="source_of",
    )
    return dataset


def ensure_schema_version(session, dataset, payload):
    schema_version = get_one_or_none(
        session,
        SchemaVersion,
        SchemaVersion.dataset_id == dataset.id,
        SchemaVersion.version_number == payload["version_number"],
        SchemaVersion.deleted_at.is_(None),
    )
    if schema_version is None:
        schema_version = SchemaVersion(dataset_id=dataset.id, **payload)
        session.add(schema_version)
        session.flush()
    else:
        schema_version.schema_json = payload["schema_json"]
    ensure_lineage_edge(
        session,
        from_entity_type="dataset",
        from_entity_id=dataset.id,
        to_entity_type="schema_version",
        to_entity_id=schema_version.id,
        relation_type="has_schema_version",
    )
    return schema_version


def ensure_dataset_version(session, dataset, schema_lookup, payload):
    dataset_version = get_one_or_none(
        session,
        DatasetVersion,
        DatasetVersion.dataset_id == dataset.id,
        DatasetVersion.version_number == payload["version_number"],
        DatasetVersion.deleted_at.is_(None),
    )
    schema_version = schema_lookup[payload["schema_version_number"]]
    if dataset_version is None:
        dataset_version = DatasetVersion(
            dataset_id=dataset.id,
            version_number=payload["version_number"],
            schema_version_id=schema_version.id,
        )
        session.add(dataset_version)
        session.flush()
    else:
        dataset_version.schema_version_id = schema_version.id
    ensure_lineage_edge(
        session,
        from_entity_type="dataset",
        from_entity_id=dataset.id,
        to_entity_type="dataset_version",
        to_entity_id=dataset_version.id,
        relation_type="has_version",
    )
    ensure_lineage_edge(
        session,
        from_entity_type="schema_version",
        from_entity_id=schema_version.id,
        to_entity_type="dataset_version",
        to_entity_id=dataset_version.id,
        relation_type="defines_schema_for",
    )
    return dataset_version


def ensure_feature_set(session, version_lookup, payload):
    feature_set = get_one_or_none(session, FeatureSet, FeatureSet.name == payload["name"], FeatureSet.deleted_at.is_(None))
    dataset_version = version_lookup[payload["dataset_version_number"]]
    if feature_set is None:
        feature_set = FeatureSet(
            name=payload["name"],
            dataset_version_id=dataset_version.id,
            feature_schema_json=payload["feature_schema_json"],
        )
        session.add(feature_set)
        session.flush()
    else:
        feature_set.dataset_version_id = dataset_version.id
        feature_set.feature_schema_json = payload["feature_schema_json"]
    ensure_lineage_edge(
        session,
        from_entity_type="dataset_version",
        from_entity_id=dataset_version.id,
        to_entity_type="feature_set",
        to_entity_id=feature_set.id,
        relation_type="produces_features",
    )
    return feature_set


def ensure_experiment(session, feature_lookup, payload):
    experiment = get_one_or_none(session, Experiment, Experiment.name == payload["name"], Experiment.deleted_at.is_(None))
    feature_set = feature_lookup[payload["feature_set_name"]]
    status = payload.get("status", "finished")
    if experiment is None:
        experiment = Experiment(
            name=payload["name"],
            feature_set_id=feature_set.id,
            parameters_json=payload["parameters_json"],
            metrics_json=payload["metrics_json"],
            status=status,
        )
        session.add(experiment)
        session.flush()
    else:
        experiment.feature_set_id = feature_set.id
        experiment.parameters_json = payload["parameters_json"]
        experiment.metrics_json = payload["metrics_json"]
        experiment.status = status
    ensure_lineage_edge(
        session,
        from_entity_type="feature_set",
        from_entity_id=feature_set.id,
        to_entity_type="experiment",
        to_entity_id=experiment.id,
        relation_type="used_in_experiment",
    )
    return experiment


DEMO_MODELS = [
    {
        "name": "titanic_logreg_v1",
        "experiment_name": "titanic_logreg_baseline",
        "framework": "sklearn",
        "version": "1.0.0",
        "artifact_path": "s3://demo-models/titanic/logreg_v1.pkl",
        "description": "Baseline logistic regression for Titanic survival.",
    },
    {
        "name": "titanic_rf_v1",
        "experiment_name": "titanic_random_forest",
        "framework": "sklearn",
        "version": "1.1.0",
        "artifact_path": "s3://demo-models/titanic/rf_v1.pkl",
        "description": "Random forest with extended feature set.",
    },
    {
        "name": "titanic_xgb_v1",
        "experiment_name": "titanic_xgboost_tuned",
        "framework": "xgboost",
        "version": "1.2.0",
        "artifact_path": "s3://demo-models/titanic/xgb_v1.json",
        "description": "Tuned XGBoost classifier on cleaned Titanic features.",
    },
    {
        "name": "house_prices_linreg_v1",
        "experiment_name": "house_prices_linear_regression",
        "framework": "sklearn",
        "version": "1.0.0",
        "artifact_path": "s3://demo-models/housing/linreg_v1.pkl",
        "description": "Linear regression baseline for house prices.",
    },
    {
        "name": "house_prices_lgbm_v1",
        "experiment_name": "house_prices_lightgbm",
        "framework": "lightgbm",
        "version": "1.0.1",
        "artifact_path": "s3://demo-models/housing/lgbm_v1.bin",
        "description": "LightGBM regressor with engineered features.",
    },
    {
        "name": "churn_logreg_v1",
        "experiment_name": "churn_logreg_baseline",
        "framework": "sklearn",
        "version": "1.0.0",
        "artifact_path": "s3://demo-models/churn/logreg_v1.pkl",
        "description": "Baseline logistic regression for telecom churn.",
    },
    {
        "name": "churn_catboost_v1",
        "experiment_name": "churn_catboost_enriched",
        "framework": "catboost",
        "version": "1.0.0",
        "artifact_path": "s3://demo-models/churn/catboost_v1.cbm",
        "description": "CatBoost on enriched churn features.",
    },
]


def ensure_model(session, experiment_lookup, payload):
    model = get_one_or_none(session, Model, Model.name == payload["name"], Model.deleted_at.is_(None))
    experiment = experiment_lookup.get(payload["experiment_name"])
    if experiment is None:
        return None
    if model is None:
        model = Model(
            name=payload["name"],
            experiment_id=experiment.id,
            framework=payload.get("framework"),
            version=payload.get("version"),
            artifact_path=payload.get("artifact_path"),
            description=payload.get("description"),
        )
        session.add(model)
        session.flush()
    else:
        model.experiment_id = experiment.id
        model.framework = payload.get("framework")
        model.version = payload.get("version")
        model.artifact_path = payload.get("artifact_path")
        model.description = payload.get("description")
    ensure_lineage_edge(
        session,
        from_entity_type="experiment",
        from_entity_id=experiment.id,
        to_entity_type="model",
        to_entity_id=model.id,
        relation_type="produces_model",
    )
    return model


def seed_demo_metadata() -> dict[str, int]:
    stats = {
        "sources": 0,
        "datasets": 0,
        "schema_versions": 0,
        "dataset_versions": 0,
        "feature_sets": 0,
        "experiments": 0,
        "models": 0,
        "lineage_edges": 0,
    }

    wait_for_database()
    with SessionLocal() as session:
        for catalog_item in DEMO_CATALOG:
            source = ensure_source(session, catalog_item["source"])
            dataset = ensure_dataset(session, source, catalog_item["dataset"])

            schema_lookup = {}
            for schema_payload in catalog_item["schemas"]:
                schema_version = ensure_schema_version(session, dataset, schema_payload)
                schema_lookup[schema_payload["version_number"]] = schema_version

            version_lookup = {}
            for version_payload in catalog_item["dataset_versions"]:
                dataset_version = ensure_dataset_version(session, dataset, schema_lookup, version_payload)
                version_lookup[version_payload["version_number"]] = dataset_version

            feature_lookup = {}
            for feature_payload in catalog_item["feature_sets"]:
                feature_set = ensure_feature_set(session, version_lookup, feature_payload)
                feature_lookup[feature_payload["name"]] = feature_set

            for experiment_payload in catalog_item["experiments"]:
                ensure_experiment(session, feature_lookup, experiment_payload)

        session.flush()

        experiment_lookup = {
            exp.name: exp
            for exp in session.scalars(
                select(Experiment).where(Experiment.deleted_at.is_(None))
            ).all()
        }
        for model_payload in DEMO_MODELS:
            ensure_model(session, experiment_lookup, model_payload)

        session.commit()

        stats["sources"] = session.scalar(select(func.count()).select_from(DataSource).where(DataSource.deleted_at.is_(None))) or 0
        stats["datasets"] = session.scalar(select(func.count()).select_from(Dataset).where(Dataset.deleted_at.is_(None))) or 0
        stats["schema_versions"] = session.scalar(select(func.count()).select_from(SchemaVersion).where(SchemaVersion.deleted_at.is_(None))) or 0
        stats["dataset_versions"] = session.scalar(select(func.count()).select_from(DatasetVersion).where(DatasetVersion.deleted_at.is_(None))) or 0
        stats["feature_sets"] = session.scalar(select(func.count()).select_from(FeatureSet).where(FeatureSet.deleted_at.is_(None))) or 0
        stats["experiments"] = session.scalar(select(func.count()).select_from(Experiment).where(Experiment.deleted_at.is_(None))) or 0
        stats["models"] = session.scalar(select(func.count()).select_from(Model).where(Model.deleted_at.is_(None))) or 0
        stats["lineage_edges"] = session.scalar(select(func.count()).select_from(LineageEdge).where(LineageEdge.deleted_at.is_(None))) or 0

    return stats


if __name__ == "__main__":
    result = seed_demo_metadata()
    print("Demo metadata seeded:")
    for key, value in result.items():
        print(f"- {key}: {value}")
