from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


class SummaryType(StrEnum):
    TECHNICAL = "technical"
    EXECUTIVE = "executive"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AiSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_type: SummaryType = SummaryType.TECHNICAL
    include_recommendations: bool = True


class ProbableCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    confidence: Confidence
    supporting_evidence: list[str] = Field(min_length=1, max_length=10)

    @field_validator("supporting_evidence")
    @classmethod
    def validate_evidence(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("supporting evidence must be non-empty and bounded")
        return values


class AiUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self) -> "AiUsage":
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        return self


class AiSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(pattern=r"^INC-[0-9]{8}-[A-F0-9]{8}$")
    summary_type: SummaryType
    summary: str = Field(min_length=1, max_length=2000)
    observed_facts: list[str] = Field(max_length=20)
    probable_causes: list[ProbableCause] = Field(max_length=10)
    recommended_actions: list[str] = Field(max_length=20)
    missing_information: list[str] = Field(max_length=20)
    limitations: list[str] = Field(min_length=1, max_length=20)
    model_id: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=100)
    generated_at: datetime
    usage: AiUsage
    latency_ms: int = Field(ge=0)

    @field_validator(
        "observed_facts",
        "recommended_actions",
        "missing_information",
        "limitations",
    )
    @classmethod
    def validate_bounded_strings(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("list values must be non-empty and bounded")
        return values


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
