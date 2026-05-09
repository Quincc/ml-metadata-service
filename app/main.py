from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401
from app.db import wait_for_database
from app.exceptions import register_exception_handlers
from app.routers.dataset import router as dataset_router
from app.routers.datasource import router as datasource_router
from app.routers.experiment import router as experiment_router
from app.routers.feature_set import router as feature_set_router
from app.routers.lineage import router as lineage_router
from app.routers.model import router as model_router
from app.routers.ui import router as ui_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    wait_for_database()
    yield


app = FastAPI(
    title="ML Metadata Management Service",
    description="Backend service for datasets, versions, schemas, feature sets and lineage.",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(datasource_router)
app.include_router(dataset_router)
app.include_router(feature_set_router)
app.include_router(experiment_router)
app.include_router(model_router)
app.include_router(lineage_router)
app.include_router(ui_router)


@app.get("/")
def read_root() -> RedirectResponse:
    return RedirectResponse(url="/ui", status_code=302)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"message": "ML Metadata Management Service is running"}
