from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


class EventCreate(BaseModel):
    source: str = Field(min_length=2, max_length=120)
    site: str = Field(min_length=2, max_length=120)
    type: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_]+$")
    message: str = Field(min_length=3, max_length=500)
    value: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class StatusUpdate(BaseModel):
    status: IncidentStatus


class Incident(BaseModel):
    incident_id: str
    event_id: str | None = None
    source: str
    site: str
    type: str
    message: str
    value: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    severity: Severity
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


class EventAccepted(BaseModel):
    event_id: str
    incident_id: str
    status: Literal["accepted"] = "accepted"
    mode: Literal["asynchronous"] = "asynchronous"
    received_at: datetime


class Metrics(BaseModel):
    total: int
    open: int
    investigating: int
    resolved: int
    critical: int
    warning: int
    info: int
    by_site: dict[str, int]
