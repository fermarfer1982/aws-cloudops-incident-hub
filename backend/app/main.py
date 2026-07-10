from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from .config import settings
from .models import (
    EventAccepted,
    EventCreate,
    Incident,
    IncidentStatus,
    Metrics,
    Severity,
    StatusUpdate,
)
from .publisher import EventPublisher
from .repository import IncidentRepository
from .service import IncidentNotFoundError, IncidentService

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)

repository = IncidentRepository()
publisher = EventPublisher() if settings.event_bus_name else None
service = IncidentService(repository, publisher=publisher)


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.ensure_local_table()
    yield


app = FastAPI(
    title="AWS CloudOps Incident Hub API",
    version="0.2.0",
    description=(
        "Local-first incident API with an asynchronous EventBridge and SQS path "
        "for AWS deployments."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def get_service() -> IncidentService:
    return service


@app.get("/health")
def health() -> dict[str, str]:
    mode = "asynchronous" if service.publisher is not None else "synchronous-local"
    return {
        "status": "ok",
        "service": "cloudops-incident-hub",
        "ingestion_mode": mode,
    }


@app.post(
    "/events",
    response_model=Incident | EventAccepted,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    event: EventCreate,
    response: Response,
    incident_service: IncidentService = Depends(get_service),
) -> dict:
    result = incident_service.ingest(event)
    if result.get("mode") == "asynchronous":
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@app.get("/events", response_model=list[Incident])
def list_events(
    limit: int = Query(default=100, ge=1, le=500),
    severity: Severity | None = None,
    incident_status: IncidentStatus | None = Query(default=None, alias="status"),
    site: str | None = Query(default=None, min_length=2, max_length=120),
    incident_service: IncidentService = Depends(get_service),
) -> list[dict]:
    return incident_service.repository.list(
        limit=limit,
        severity=severity.value if severity else None,
        status=incident_status.value if incident_status else None,
        site=site,
    )


@app.patch("/events/{incident_id}/status", response_model=Incident)
def update_event_status(
    incident_id: str,
    update: StatusUpdate,
    incident_service: IncidentService = Depends(get_service),
) -> dict:
    try:
        return incident_service.update_status(incident_id, update.status)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc


@app.get("/metrics", response_model=Metrics)
def get_metrics(incident_service: IncidentService = Depends(get_service)) -> dict:
    return incident_service.metrics()


handler = Mangum(app, lifespan="off")
