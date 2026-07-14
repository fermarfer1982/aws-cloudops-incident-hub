from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.config import Settings
from app.models import (
    AiSummaryRequest,
    AiSummaryResponse,
    AiUsage,
    ProbableCause,
)

from .client import (
    BedrockClient,
    BedrockClientUnavailableError,
    BedrockRequest,
)
from .prompt import build_prompt
from .redaction import redact_incident

INCIDENT_ID_PATTERN = re.compile(r"^INC-[0-9]{8}-[A-F0-9]{8}$")
FACT_FIELDS = (
    ("incident_id", "Incident ID"),
    ("severity", "Severity"),
    ("status", "Status"),
    ("source", "Source"),
    ("site", "Site"),
    ("type", "Type"),
    ("message", "Message"),
    ("value", "Value"),
)


class ReadOnlyIncidentRepository(Protocol):
    def get(self, incident_id: str) -> dict[str, Any] | None: ...


class AiSummaryError(RuntimeError):
    pass


class AiSummaryDisabledError(AiSummaryError):
    pass


class AiSummaryProviderUnavailableError(AiSummaryError):
    pass


class AiSummaryIncidentNotFoundError(AiSummaryError):
    pass


class AiSummaryInvalidIncidentIdError(AiSummaryError):
    pass


class AiSummaryContextTooLargeError(AiSummaryError):
    pass


class AiSummaryResponseError(AiSummaryError):
    pass


class AiSummaryGroundingError(AiSummaryResponseError):
    pass


class AiSummaryTimeoutError(AiSummaryError):
    pass


class ProviderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    probable_causes: list[ProbableCause] = Field(max_length=10)
    recommended_actions: list[str] = Field(max_length=20)
    missing_information: list[str] = Field(max_length=20)
    limitations: list[str] = Field(min_length=1, max_length=20)

    @field_validator("recommended_actions", "missing_information", "limitations")
    @classmethod
    def validate_bounded_strings(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("provider list values must be non-empty and bounded")
        return values


def build_observed_facts(incident: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    for key, label in FACT_FIELDS:
        value = incident.get(key)
        if value is not None and value != "":
            facts.append(f"{label}: {value}")
    return facts


class IncidentSummaryService:
    def __init__(
        self,
        repository: ReadOnlyIncidentRepository,
        client: BedrockClient,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._client = client
        self._settings = settings

    def summarize(
        self,
        incident_id: str,
        request: AiSummaryRequest,
    ) -> AiSummaryResponse:
        if not self._settings.ai_summary_enabled:
            raise AiSummaryDisabledError("AI summaries are disabled")
        if not INCIDENT_ID_PATTERN.fullmatch(incident_id):
            raise AiSummaryInvalidIncidentIdError("Invalid incident identifier")

        incident = self._repository.get(incident_id)
        if incident is None:
            raise AiSummaryIncidentNotFoundError("Incident not found")

        sanitized = redact_incident(incident)
        observed_facts = build_observed_facts(sanitized)
        prompt = build_prompt(
            incident=sanitized,
            allowed_evidence=observed_facts,
            prompt_version=self._settings.ai_summary_prompt_version,
        )
        if len(prompt.user_message) > self._settings.ai_summary_max_context_chars:
            raise AiSummaryContextTooLargeError("Incident context is too large")

        provider_request = BedrockRequest(
            system_prompt=prompt.system_prompt,
            user_message=prompt.user_message,
            prompt_version=self._settings.ai_summary_prompt_version,
            model_id=self._settings.ai_summary_model_id,
            summary_type=request.summary_type,
            allowed_evidence=tuple(observed_facts),
            include_recommendations=request.include_recommendations,
        )
        try:
            result = self._client.converse(provider_request)
        except BedrockClientUnavailableError as exc:
            raise AiSummaryProviderUnavailableError("AI summary provider is unavailable") from exc
        except TimeoutError as exc:
            raise AiSummaryTimeoutError("AI summary provider timed out") from exc

        if not result.text or len(result.text) > self._settings.ai_summary_max_output_chars:
            raise AiSummaryResponseError("AI summary response is invalid")
        try:
            raw_payload = json.loads(result.text)
            payload = ProviderPayload.model_validate(raw_payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise AiSummaryResponseError("AI summary response is invalid") from exc

        allowed = set(observed_facts)
        for cause in payload.probable_causes:
            if not cause.supporting_evidence:
                raise AiSummaryGroundingError("AI summary evidence is invalid")
            if any(evidence not in allowed for evidence in cause.supporting_evidence):
                raise AiSummaryGroundingError("AI summary evidence is invalid")

        recommendations = (
            payload.recommended_actions if request.include_recommendations else []
        )
        input_tokens = max(result.input_tokens, 0)
        output_tokens = max(result.output_tokens, 0)
        return AiSummaryResponse(
            incident_id=incident_id,
            summary_type=request.summary_type,
            summary=payload.summary,
            observed_facts=observed_facts,
            probable_causes=payload.probable_causes,
            recommended_actions=recommendations,
            missing_information=payload.missing_information,
            limitations=payload.limitations,
            model_id=self._settings.ai_summary_model_id,
            prompt_version=self._settings.ai_summary_prompt_version,
            generated_at=datetime.now(timezone.utc),
            usage=AiUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            latency_ms=max(result.latency_ms, 0),
        )
