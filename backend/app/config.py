from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    aws_region: str = os.getenv("AWS_REGION", "eu-west-1")
    table_name: str = os.getenv("TABLE_NAME", "cloudops-incidents")
    dynamodb_endpoint: str | None = os.getenv("DYNAMODB_ENDPOINT") or None
    cors_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("CORS_ORIGINS", "*").split(",")
        if value.strip()
    )


settings = Settings()
