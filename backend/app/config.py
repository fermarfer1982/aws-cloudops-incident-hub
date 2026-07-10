from __future__ import annotations

import os
from dataclasses import dataclass


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    )


@dataclass(frozen=True)
class Settings:
    aws_region: str = os.getenv("AWS_REGION", "eu-west-1")
    table_name: str = os.getenv("TABLE_NAME", "cloudops-incidents-v2")
    metrics_table_name: str = os.getenv(
        "METRICS_TABLE_NAME",
        "cloudops-incident-metrics-v2",
    )
    dynamodb_endpoint: str | None = os.getenv("DYNAMODB_ENDPOINT") or None
    event_bus_name: str | None = os.getenv("EVENT_BUS_NAME") or None
    event_source: str = os.getenv("EVENT_SOURCE", "cloudops.incident-hub")
    cors_origins: tuple[str, ...] = _csv_env(
        "CORS_ORIGINS",
        "http://localhost:8081,http://192.168.0.50:8081,http://mirofish:8081",
    )


settings = Settings()
