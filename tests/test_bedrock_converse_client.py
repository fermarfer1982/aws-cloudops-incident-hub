from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from app.config import Settings
from app.genai.client import (
    BedrockClientResponseError,
    BedrockClientUnavailableError,
    BedrockConverseClient,
    BedrockRequest,
)
from app.models import SummaryType


class StubRuntimeClient:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def request() -> BedrockRequest:
    return BedrockRequest(
        system_prompt="system",
        user_message="user context",
        prompt_version="incident-summary-v1",
        model_id="approved-model-placeholder",
        summary_type=SummaryType.TECHNICAL,
        allowed_evidence=("Status: open",),
        include_recommendations=True,
    )


def valid_response() -> dict[str, Any]:
    return {
        "output": {"message": {"content": [{"text": '{"summary":"safe"}'}]}},
        "usage": {"inputTokens": 12, "outputTokens": 7, "totalTokens": 19},
        "metrics": {"latencyMs": 999},
        "stopReason": "end_turn",
    }


def test_converse_maps_the_request_and_response_without_network():
    runtime = StubRuntimeClient(valid_response())
    client = BedrockConverseClient(
        runtime,
        max_tokens=800,
        temperature=0.0,
    )

    result = client.converse(request())

    assert runtime.calls == [
        {
            "modelId": "approved-model-placeholder",
            "system": [{"text": "system"}],
            "messages": [{"role": "user", "content": [{"text": "user context"}]}],
            "inferenceConfig": {"maxTokens": 800, "temperature": 0.0},
        }
    ]
    assert result.text == '{"summary":"safe"}'
    assert result.input_tokens == 12
    assert result.output_tokens == 7
    assert result.total_tokens == 19
    assert result.latency_ms == 999
    assert result.model_id == "approved-model-placeholder"


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"output": {"message": {"content": []}}, "usage": {}},
        {
            "output": {"message": {"content": [{"image": {}}]}},
            "usage": {"inputTokens": 1, "outputTokens": 1},
        },
        {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "usage": {"inputTokens": -1, "outputTokens": 1},
        },
        {
            "output": {"message": {"content": [{"text": "ok"}]}},
            "usage": {"inputTokens": True, "outputTokens": 1},
        },
    ],
)
def test_converse_rejects_malformed_provider_responses(response):
    client = BedrockConverseClient(
        StubRuntimeClient(response), max_tokens=800, temperature=0.0
    )
    with pytest.raises(BedrockClientResponseError):
        client.converse(request())


@pytest.mark.parametrize(
    "stop_reason",
    [
        "max_tokens",
        "stop_sequence",
        "guardrail_intervened",
        "content_filtered",
        "tool_use",
        "malformed_model_output",
        "model_context_window_exceeded",
        "",
        None,
    ],
)
def test_converse_fails_closed_for_non_terminal_stop_reasons(stop_reason):
    response = valid_response()
    response["stopReason"] = stop_reason
    client = BedrockConverseClient(
        StubRuntimeClient(response), max_tokens=800, temperature=0.0
    )
    with pytest.raises(BedrockClientResponseError):
        client.converse(request())


@pytest.mark.parametrize("total_tokens", [18, -1, 19.0, True])
def test_converse_validates_total_tokens(total_tokens):
    response = valid_response()
    response["usage"]["totalTokens"] = total_tokens
    client = BedrockConverseClient(
        StubRuntimeClient(response), max_tokens=800, temperature=0.0
    )
    with pytest.raises(BedrockClientResponseError):
        client.converse(request())


@pytest.mark.parametrize("latency_ms", [-1, 1.5, True, None])
def test_converse_validates_provider_latency(latency_ms):
    response = valid_response()
    response["metrics"]["latencyMs"] = latency_ms
    client = BedrockConverseClient(
        StubRuntimeClient(response), max_tokens=800, temperature=0.0
    )
    with pytest.raises(BedrockClientResponseError):
        client.converse(request())


def test_converse_normalizes_timeout_without_exposing_payload():
    error = ReadTimeoutError(endpoint_url="https://synthetic.invalid")
    client = BedrockConverseClient(
        StubRuntimeClient(error=error), max_tokens=800, temperature=0.0
    )
    with pytest.raises(TimeoutError, match="request timed out"):
        client.converse(request())


def test_converse_normalizes_sdk_errors_without_exposing_payload():
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "synthetic"}},
        "Converse",
    )
    client = BedrockConverseClient(
        StubRuntimeClient(error=error), max_tokens=800, temperature=0.0
    )
    with pytest.raises(BedrockClientUnavailableError, match="request failed"):
        client.converse(request())


@pytest.mark.parametrize(
    ("enabled", "provider", "expected_type"),
    [
        (False, "disabled", "DisabledBedrockClient"),
        (False, "fake", "DisabledBedrockClient"),
        (True, "fake", "FakeBedrockClient"),
    ],
)
def test_non_bedrock_providers_never_construct_an_sdk_client(
    monkeypatch, enabled, provider, expected_type
):
    import app.main as main_module

    configured = Settings(
        ai_summary_enabled=enabled,
        ai_summary_provider=provider,
    )
    monkeypatch.setattr(main_module, "settings", configured)

    def unexpected_client(*args, **kwargs):
        del args, kwargs
        raise AssertionError("boto3 client must not be constructed")

    monkeypatch.setattr(main_module.boto3, "client", unexpected_client)
    assert type(main_module.build_ai_summary_client()).__name__ == expected_type


def test_bedrock_provider_builds_the_injected_runtime_adapter(monkeypatch):
    import app.main as main_module

    configured = Settings(
        ai_summary_enabled=True,
        ai_summary_provider="bedrock",
        ai_summary_model_id="approved-model-placeholder",
        ai_summary_allowed_model_ids=("approved-model-placeholder",),
    )
    monkeypatch.setattr(main_module, "settings", configured)
    runtime = StubRuntimeClient(valid_response())
    calls = []

    def fake_client(service_name, **kwargs):
        calls.append((service_name, kwargs))
        return runtime

    monkeypatch.setattr(main_module.boto3, "client", fake_client)
    built = main_module.build_ai_summary_client()

    assert isinstance(built, BedrockConverseClient)
    assert calls[0][0] == "bedrock-runtime"
    assert calls[0][1]["region_name"] == configured.aws_region
    sdk_config = calls[0][1]["config"]
    assert sdk_config.connect_timeout == 3.0
    assert sdk_config.read_timeout == 30.0
    assert sdk_config.retries == {"total_max_attempts": 2, "mode": "standard"}


def test_bedrock_client_is_created_lazily_by_the_endpoint_dependency(monkeypatch):
    import app.main as main_module

    configured = Settings(
        ai_summary_enabled=True,
        ai_summary_provider="bedrock",
        ai_summary_model_id="approved-model-placeholder",
        ai_summary_allowed_model_ids=("approved-model-placeholder",),
    )
    runtime = StubRuntimeClient(valid_response())
    calls = []
    monkeypatch.setattr(main_module, "settings", configured)
    monkeypatch.setattr(
        main_module.boto3,
        "client",
        lambda service_name, **kwargs: calls.append((service_name, kwargs)) or runtime,
    )
    main_module.get_ai_summary_service.cache_clear()

    assert calls == []
    try:
        service = main_module.get_ai_summary_service()
        assert isinstance(service._client, BedrockConverseClient)
        assert [call[0] for call in calls] == ["bedrock-runtime"]
        assert main_module.get_ai_summary_service() is service
        assert len(calls) == 1
    finally:
        main_module.get_ai_summary_service.cache_clear()
