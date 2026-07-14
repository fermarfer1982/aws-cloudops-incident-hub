from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    )


def parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(
        f"{name} must be one of true, 1, yes, on, false, 0, no, or off"
    )


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _temperature_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


@dataclass(frozen=True)
class Settings:
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "eu-west-1"))
    table_name: str = field(
        default_factory=lambda: os.getenv("TABLE_NAME", "cloudops-incidents-v2")
    )
    metrics_table_name: str = field(
        default_factory=lambda: os.getenv(
            "METRICS_TABLE_NAME", "cloudops-incident-metrics-v2"
        )
    )
    dynamodb_endpoint: str | None = field(
        default_factory=lambda: os.getenv("DYNAMODB_ENDPOINT") or None
    )
    event_bus_name: str | None = field(
        default_factory=lambda: os.getenv("EVENT_BUS_NAME") or None
    )
    event_source: str = field(
        default_factory=lambda: os.getenv("EVENT_SOURCE", "cloudops.incident-hub")
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "CORS_ORIGINS",
            "http://localhost:8081,http://192.168.0.50:8081,http://mirofish:8081",
        )
    )
    ai_summary_enabled: bool = field(
        default_factory=lambda: parse_bool(
            os.getenv("AI_SUMMARY_ENABLED", "false"), name="AI_SUMMARY_ENABLED"
        )
    )
    ai_summary_provider: str = field(
        default_factory=lambda: os.getenv("AI_SUMMARY_PROVIDER", "disabled").lower()
    )
    ai_summary_model_id: str = field(
        default_factory=lambda: os.getenv("AI_SUMMARY_MODEL_ID", "fake-local-model")
    )
    ai_summary_allowed_model_ids: tuple[str, ...] = field(
        default_factory=lambda: _csv_env("AI_SUMMARY_ALLOWED_MODEL_IDS", "")
    )
    ai_summary_prompt_version: str = field(
        default_factory=lambda: os.getenv(
            "AI_SUMMARY_PROMPT_VERSION", "incident-summary-v1"
        )
    )
    ai_summary_max_context_chars: int = field(
        default_factory=lambda: _positive_int_env("AI_SUMMARY_MAX_CONTEXT_CHARS", 8000)
    )
    ai_summary_max_output_chars: int = field(
        default_factory=lambda: _positive_int_env("AI_SUMMARY_MAX_OUTPUT_CHARS", 6000)
    )
    ai_summary_max_tokens: int = field(
        default_factory=lambda: _positive_int_env("AI_SUMMARY_MAX_TOKENS", 800)
    )
    ai_summary_temperature: float = field(
        default_factory=lambda: _temperature_env("AI_SUMMARY_TEMPERATURE", 0.0)
    )
    ai_summary_connect_timeout_seconds: float = field(
        default_factory=lambda: _positive_float_env(
            "AI_SUMMARY_CONNECT_TIMEOUT_SECONDS", 3.0
        )
    )
    ai_summary_read_timeout_seconds: float = field(
        default_factory=lambda: _positive_float_env(
            "AI_SUMMARY_READ_TIMEOUT_SECONDS", 30.0
        )
    )
    ai_summary_max_attempts: int = field(
        default_factory=lambda: _positive_int_env("AI_SUMMARY_MAX_ATTEMPTS", 2)
    )

    def __post_init__(self) -> None:
        if self.ai_summary_provider not in {"disabled", "fake", "bedrock"}:
            raise ValueError("AI_SUMMARY_PROVIDER must be disabled, fake, or bedrock")
        if self.ai_summary_max_tokens <= 0:
            raise ValueError("AI_SUMMARY_MAX_TOKENS must be positive")
        if not 0 <= self.ai_summary_temperature <= 1:
            raise ValueError("AI_SUMMARY_TEMPERATURE must be between 0 and 1")
        if self.ai_summary_connect_timeout_seconds <= 0:
            raise ValueError("AI_SUMMARY_CONNECT_TIMEOUT_SECONDS must be positive")
        if self.ai_summary_read_timeout_seconds <= 0:
            raise ValueError("AI_SUMMARY_READ_TIMEOUT_SECONDS must be positive")
        if not 1 <= self.ai_summary_max_attempts <= 5:
            raise ValueError("AI_SUMMARY_MAX_ATTEMPTS must be between 1 and 5")
        if self.ai_summary_provider == "bedrock":
            if not self.ai_summary_enabled:
                raise ValueError("AI_SUMMARY_ENABLED must be true for provider bedrock")
            if not self.ai_summary_model_id.strip():
                raise ValueError("AI_SUMMARY_MODEL_ID is required for provider bedrock")
            if self.ai_summary_model_id == "fake-local-model":
                raise ValueError("AI_SUMMARY_MODEL_ID must not be fake-local-model")
            if not self.ai_summary_allowed_model_ids:
                raise ValueError(
                    "AI_SUMMARY_ALLOWED_MODEL_IDS is required for provider bedrock"
                )
            if self.ai_summary_model_id not in self.ai_summary_allowed_model_ids:
                raise ValueError(
                    "AI_SUMMARY_MODEL_ID must be explicitly allowed for provider bedrock"
                )


settings = Settings()
