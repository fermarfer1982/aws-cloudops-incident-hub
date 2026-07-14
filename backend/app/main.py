from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import lru_cache

import boto3
from botocore.config import Config
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from .config import settings
from .genai.client import (
    BedrockConverseClient,
    DisabledBedrockClient,
    FakeBedrockClient,
)
from .genai.service import (
    AiSummaryContextTooLargeError,
    AiSummaryDisabledError,
    AiSummaryGroundingError,
    AiSummaryIncidentNotFoundError,
    AiSummaryInvalidIncidentIdError,
    AiSummaryProviderUnavailableError,
    AiSummaryResponseError,
    AiSummaryTimeoutError,
    IncidentSummaryService,
)
from .models import (
    AiSummaryRequest,
    AiSummaryResponse,
    EventAccepted,
    EventCreate,
    Incident,
    IncidentStatus,
    Metrics,
    Severity,
    StatusUpdate,
)
from .pagination import InvalidContinuationToken, PaginatedIncidentRepository
from .publisher import EventPublisher
from .service import IncidentNotFoundError, IncidentService

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)

repository = PaginatedIncidentRepository()
publisher = EventPublisher() if settings.event_bus_name else None
service = IncidentService(repository, publisher=publisher)


def build_ai_summary_client():
    if not settings.ai_summary_enabled or settings.ai_summary_provider == "disabled":
        return DisabledBedrockClient()
    if settings.ai_summary_provider == "fake":
        return FakeBedrockClient()
    runtime_client = boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        config=Config(
            connect_timeout=settings.ai_summary_connect_timeout_seconds,
            read_timeout=settings.ai_summary_read_timeout_seconds,
            retries={
                "total_max_attempts": settings.ai_summary_max_attempts,
                "mode": "standard",
            },
        ),
    )
    return BedrockConverseClient(
        runtime_client,
        max_tokens=settings.ai_summary_max_tokens,
        temperature=settings.ai_summary_temperature,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.ensure_local_table()
    yield


app = FastAPI(
    title="AWS CloudOps Incident Hub API",
    version="0.4.0",
    description=(
        "Local-first incident API. AWS deployments use Cognito JWT authorization "
        "at API Gateway and asynchronous EventBridge/SQS processing."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["X-Next-Token"],
)


def get_service() -> IncidentService:
    return service


@lru_cache
def get_ai_summary_service() -> IncidentSummaryService:
    return IncidentSummaryService(repository, build_ai_summary_client(), settings)


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
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    severity: Severity | None = None,
    incident_status: IncidentStatus | None = Query(default=None, alias="status"),
    site: str | None = Query(default=None, min_length=2, max_length=120),
    next_token: str | None = Query(default=None, min_length=1, max_length=4096),
    incident_service: IncidentService = Depends(get_service),
) -> list[dict]:
    try:
        page = incident_service.repository.list_page(
            limit=limit,
            severity=severity.value if severity else None,
            status=incident_status.value if incident_status else None,
            site=site,
            continuation_token=next_token,
        )
    except InvalidContinuationToken as exc:
        raise HTTPException(status_code=400, detail="Invalid continuation token") from exc

    if page.next_token:
        response.headers["X-Next-Token"] = page.next_token
    return page.items


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


@app.post(
    "/incidents/{incident_id}/ai-summary",
    response_model=AiSummaryResponse,
)
def create_ai_summary(
    incident_id: str,
    request: AiSummaryRequest | None = Body(default=None),
    summary_service: IncidentSummaryService = Depends(get_ai_summary_service),
) -> AiSummaryResponse:
    try:
        return summary_service.summarize(incident_id, request or AiSummaryRequest())
    except AiSummaryIncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc
    except AiSummaryContextTooLargeError as exc:
        raise HTTPException(status_code=413, detail="Incident context is too large") from exc
    except (AiSummaryResponseError, AiSummaryGroundingError) as exc:
        raise HTTPException(status_code=502, detail="AI summary response is invalid") from exc
    except (AiSummaryDisabledError, AiSummaryProviderUnavailableError) as exc:
        raise HTTPException(status_code=503, detail="AI summary service is unavailable") from exc
    except AiSummaryTimeoutError as exc:
        raise HTTPException(status_code=504, detail="AI summary provider timed out") from exc
    except AiSummaryInvalidIncidentIdError as exc:
        raise HTTPException(status_code=422, detail="Invalid incident identifier") from exc


handler = Mangum(app, lifespan="off")
