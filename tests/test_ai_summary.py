from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.config import Settings, parse_bool
from app.genai.client import (
    BedrockRequest,
    BedrockResult,
    DisabledBedrockClient,
    FakeBedrockClient,
)
from app.genai.service import (
    AiSummaryContextTooLargeError,
    AiSummaryDisabledError,
    AiSummaryGroundingError,
    AiSummaryIncidentNotFoundError,
    AiSummaryInvalidIncidentIdError,
    AiSummaryProviderUnavailableError,
    AiSummaryResponseError,
    IncidentSummaryService,
)
from app.main import app, get_ai_summary_service
from app.models import AiSummaryRequest, AiUsage, SummaryType

INCIDENT_ID = "INC-20260714-ABCDEF12"


def make_settings(**changes) -> Settings:
    base = Settings(
        ai_summary_enabled=True,
        ai_summary_provider="fake",
        ai_summary_model_id="fake-local-model",
        ai_summary_prompt_version="incident-summary-v1",
        ai_summary_max_context_chars=8000,
        ai_summary_max_output_chars=6000,
    )
    return replace(base, **changes)


def synthetic_incident() -> dict:
    now = datetime(2026, 7, 14, tzinfo=timezone.utc).isoformat()
    return {
        "incident_id": INCIDENT_ID,
        "source": "pbs-01",
        "site": "Calahorra",
        "type": "BACKUP_FAILED",
        "message": "Nightly backup failed",
        "value": 96.2,
        "metadata": {"password": "synthetic-only", "safe": "context"},
        "severity": "critical",
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }


class ReadOnlyRepository:
    def __init__(self, incident: dict | None = None):
        self.incident = incident
        self.get_calls = 0

    def get(self, incident_id: str) -> dict | None:
        self.get_calls += 1
        return self.incident if incident_id == INCIDENT_ID else None


class StaticClient:
    def __init__(self, payload=None, *, text=None, model_id="untrusted-model"):
        self.payload = payload
        self.text = text
        self.model_id = model_id
        self.calls: list[BedrockRequest] = []

    def converse(self, request: BedrockRequest) -> BedrockResult:
        self.calls.append(request)
        text = self.text if self.text is not None else json.dumps(self.payload)
        return BedrockResult(
            text=text,
            input_tokens=10,
            output_tokens=5,
            latency_ms=2,
            model_id=self.model_id,
        )


def valid_provider_payload(evidence="Incident ID: INC-20260714-ABCDEF12") -> dict:
    return {
        "summary": "Synthetic summary.",
        "probable_causes": [
            {
                "description": "Investigation is required.",
                "confidence": "low",
                "supporting_evidence": [evidence],
            }
        ],
        "recommended_actions": ["Collect additional evidence."],
        "missing_information": [],
        "limitations": ["Synthetic local response."],
    }


@pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE"])
def test_parse_bool_true(value):
    assert parse_bool(value, name="FLAG") is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE"])
def test_parse_bool_false(value):
    assert parse_bool(value, name="FLAG") is False


def test_parse_bool_rejects_invalid_value():
    with pytest.raises(ValueError, match="FLAG must be one of"):
        parse_bool("sometimes", name="FLAG")


def test_settings_rejects_invalid_boolean_environment(monkeypatch):
    monkeypatch.setenv("AI_SUMMARY_ENABLED", "sometimes")
    with pytest.raises(ValueError, match="AI_SUMMARY_ENABLED must be one of"):
        Settings()


def test_request_defaults_and_valid_summary_types():
    assert AiSummaryRequest() == AiSummaryRequest(
        summary_type=SummaryType.TECHNICAL,
        include_recommendations=True,
    )
    assert AiSummaryRequest(summary_type="technical").summary_type is SummaryType.TECHNICAL
    assert AiSummaryRequest(summary_type="executive").summary_type is SummaryType.EXECUTIVE


@pytest.mark.parametrize("payload", [
    {"summary_type": "invalid"},
    {"unknown": True},
    {"model_id": "not-allowed"},
    {"prompt": "not-allowed"},
    {"tools": []},
])
def test_request_rejects_invalid_or_unknown_input(payload):
    with pytest.raises(ValidationError):
        AiSummaryRequest.model_validate(payload)


def test_usage_requires_consistent_total():
    with pytest.raises(ValidationError):
        AiUsage(input_tokens=1, output_tokens=2, total_tokens=99)


def test_feature_disabled_before_repository_access():
    repository = ReadOnlyRepository(synthetic_incident())
    service = IncidentSummaryService(
        repository,
        FakeBedrockClient(),
        make_settings(ai_summary_enabled=False),
    )
    with pytest.raises(AiSummaryDisabledError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())
    assert repository.get_calls == 0


def test_disabled_provider_fails_closed():
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()),
        DisabledBedrockClient(),
        make_settings(),
    )
    with pytest.raises(AiSummaryProviderUnavailableError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())


def test_invalid_id_never_reads_repository():
    repository = ReadOnlyRepository(synthetic_incident())
    service = IncidentSummaryService(repository, FakeBedrockClient(), make_settings())
    with pytest.raises(AiSummaryInvalidIncidentIdError):
        service.summarize("../../unsafe", AiSummaryRequest())
    assert repository.get_calls == 0


def test_incident_not_found():
    service = IncidentSummaryService(ReadOnlyRepository(), FakeBedrockClient(), make_settings())
    with pytest.raises(AiSummaryIncidentNotFoundError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())


def test_context_too_large_before_client_call():
    client = StaticClient(valid_provider_payload())
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()),
        client,
        make_settings(ai_summary_max_context_chars=20),
    )
    with pytest.raises(AiSummaryContextTooLargeError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())
    assert client.calls == []


@pytest.mark.parametrize("summary_type", [SummaryType.TECHNICAL, SummaryType.EXECUTIVE])
def test_fake_response_is_valid_deterministic_and_grounded(summary_type):
    repository = ReadOnlyRepository(synthetic_incident())
    client = FakeBedrockClient()
    service = IncidentSummaryService(repository, client, make_settings())

    first = service.summarize(INCIDENT_ID, AiSummaryRequest(summary_type=summary_type))
    second = service.summarize(INCIDENT_ID, AiSummaryRequest(summary_type=summary_type))

    assert first.summary == second.summary
    assert first.usage == second.usage
    assert first.latency_ms == 1
    assert first.summary_type is summary_type
    assert first.model_id == "fake-local-model"
    assert first.prompt_version == "incident-summary-v1"
    assert first.generated_at.tzinfo is not None
    assert first.generated_at.utcoffset().total_seconds() == 0
    assert repository.get_calls == 2
    assert first.observed_facts == [
        f"Incident ID: {INCIDENT_ID}",
        "Severity: critical",
        "Status: open",
        "Source: pbs-01",
        "Site: Calahorra",
        "Type: BACKUP_FAILED",
        "Message: Nightly backup failed",
        "Value: 96.2",
    ]
    assert first.probable_causes[0].supporting_evidence[0] in first.observed_facts


def test_recommendations_can_be_disabled():
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), FakeBedrockClient(), make_settings()
    )
    response = service.summarize(
        INCIDENT_ID, AiSummaryRequest(include_recommendations=False)
    )
    assert response.recommended_actions == []


@pytest.mark.parametrize("text", ["", "not-json", "[]"])
def test_invalid_provider_text_is_rejected(text):
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), StaticClient(text=text), make_settings()
    )
    with pytest.raises(AiSummaryResponseError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())


@pytest.mark.parametrize("mutation", [
    lambda payload: payload.update({"unknown": "field"}),
    lambda payload: payload.update({"summary": 42}),
    lambda payload: payload.update({"incident_id": "INC-20990101-FFFFFFFF"}),
    lambda payload: payload.update({"limitations": [""]}),
])
def test_provider_cannot_add_fields_or_wrong_types(mutation):
    payload = valid_provider_payload()
    mutation(payload)
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), StaticClient(payload), make_settings()
    )
    with pytest.raises(AiSummaryResponseError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())


def test_ungrounded_evidence_is_rejected():
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()),
        StaticClient(valid_provider_payload("Invented metric: 99")),
        make_settings(),
    )
    with pytest.raises(AiSummaryGroundingError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())


def test_cause_without_evidence_is_rejected_by_schema():
    payload = valid_provider_payload()
    payload["probable_causes"][0]["supporting_evidence"] = []
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), StaticClient(payload), make_settings()
    )
    with pytest.raises(AiSummaryResponseError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())


def test_output_too_large_is_rejected():
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()),
        StaticClient(valid_provider_payload()),
        make_settings(ai_summary_max_output_chars=10),
    )
    with pytest.raises(AiSummaryResponseError):
        service.summarize(INCIDENT_ID, AiSummaryRequest())


def test_client_metadata_cannot_override_application_metadata():
    client = StaticClient(valid_provider_payload(), model_id="provider-controlled")
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), client, make_settings()
    )
    response = service.summarize(INCIDENT_ID, AiSummaryRequest())
    assert response.incident_id == INCIDENT_ID
    assert response.model_id == "fake-local-model"
    assert response.observed_facts[0] == f"Incident ID: {INCIDENT_ID}"
    assert response.usage.total_tokens == 15


def endpoint_client(client, summary_service):
    app.dependency_overrides[get_ai_summary_service] = lambda: summary_service
    return client


def test_endpoint_disabled(client):
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()),
        FakeBedrockClient(),
        make_settings(ai_summary_enabled=False),
    )
    response = endpoint_client(client, service).post(f"/incidents/{INCIDENT_ID}/ai-summary")
    assert response.status_code == 503
    assert response.json() == {"detail": "AI summary service is unavailable"}


def test_endpoint_not_found(client):
    service = IncidentSummaryService(ReadOnlyRepository(), FakeBedrockClient(), make_settings())
    response = endpoint_client(client, service).post(f"/incidents/{INCIDENT_ID}/ai-summary")
    assert response.status_code == 404


def test_endpoint_context_too_large(client):
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()),
        FakeBedrockClient(),
        make_settings(ai_summary_max_context_chars=20),
    )
    response = endpoint_client(client, service).post(f"/incidents/{INCIDENT_ID}/ai-summary")
    assert response.status_code == 413


def test_endpoint_invalid_provider_response(client):
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), StaticClient(text="invalid"), make_settings()
    )
    response = endpoint_client(client, service).post(f"/incidents/{INCIDENT_ID}/ai-summary")
    assert response.status_code == 502
    assert response.json() == {"detail": "AI summary response is invalid"}


def test_endpoint_provider_timeout(client):
    class TimeoutClient:
        def converse(self, request):
            del request
            raise TimeoutError("synthetic timeout")

    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), TimeoutClient(), make_settings()
    )
    response = endpoint_client(client, service).post(f"/incidents/{INCIDENT_ID}/ai-summary")
    assert response.status_code == 504
    assert response.json() == {"detail": "AI summary provider timed out"}


def test_endpoint_valid_optional_body_and_validation(client):
    service = IncidentSummaryService(
        ReadOnlyRepository(synthetic_incident()), FakeBedrockClient(), make_settings()
    )
    test_client = endpoint_client(client, service)
    default_response = test_client.post(f"/incidents/{INCIDENT_ID}/ai-summary")
    assert default_response.status_code == 200
    assert default_response.json()["summary_type"] == "technical"

    executive = test_client.post(
        f"/incidents/{INCIDENT_ID}/ai-summary",
        json={"summary_type": "executive", "include_recommendations": False},
    )
    assert executive.status_code == 200
    assert executive.json()["summary_type"] == "executive"
    assert executive.json()["recommended_actions"] == []

    assert test_client.post(
        f"/incidents/{INCIDENT_ID}/ai-summary", json={"unknown": True}
    ).status_code == 422
    assert test_client.post(
        f"/incidents/{INCIDENT_ID}/ai-summary", json={"summary_type": "invalid"}
    ).status_code == 422


def test_endpoint_invalid_id_does_not_read_repository(client):
    repository = ReadOnlyRepository(synthetic_incident())
    service = IncidentSummaryService(repository, FakeBedrockClient(), make_settings())
    response = endpoint_client(client, service).post("/incidents/not-valid/ai-summary")
    assert response.status_code == 422
    assert repository.get_calls == 0
