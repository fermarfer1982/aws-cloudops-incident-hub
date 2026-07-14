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

    def __post_init__(self) -> None:
        if self.ai_summary_provider not in {"disabled", "fake"}:
            raise ValueError("AI_SUMMARY_PROVIDER must be disabled or fake")


settings = Settings()
