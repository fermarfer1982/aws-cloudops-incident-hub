#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "backend" / "app" / "repository.py"
SERVICE = ROOT / "backend" / "app" / "service.py"
CONFIG = ROOT / "backend" / "app" / "config.py"
STACK = ROOT / "infrastructure" / "cloudops_infra" / "stack.py"
COMPOSE = ROOT / "docker-compose.yml"
DOC = ROOT / "docs" / "p0-production-controls.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    for path in (REPOSITORY, SERVICE, CONFIG, STACK, COMPOSE, DOC):
        require(path.is_file(), f"Missing required P0 control artifact: {path}")

    repository = REPOSITORY.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    stack = STACK.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")

    for source, content in ((REPOSITORY, repository), (SERVICE, service)):
        require(".scan(" not in content, f"Operational DynamoDB Scan found in {source}")

    for index_name in (
        "incidents-by-time",
        "incidents-by-site",
        "incidents-by-status",
        "incidents-by-severity",
    ):
        require(index_name in repository, f"Repository missing query index: {index_name}")
        require(index_name in stack, f"CDK stack missing query index: {index_name}")

    for token in (
        "metrics_table_name",
        "transact_write_items",
        "KeyConditionExpression",
        "SITE_METRIC_GROUP",
    ):
        require(token in repository, f"Repository missing P0 data control: {token}")

    for token in (
        "HttpJwtAuthorizer",
        "cognito.UserPool",
        "incidents.read",
        "incidents.write",
        "incidents.manage",
        "authorization_scopes",
        "allowed_origins must be a non-empty explicit allowlist",
    ):
        require(token in stack, f"CDK stack missing P0 security control: {token}")

    require('os.getenv("CORS_ORIGINS", "*")' not in config, "Config still defaults CORS to wildcard")
    require('CORS_ORIGINS: "*"' not in compose, "Docker Compose still enables wildcard CORS")
    require("METRICS_TABLE_NAME:" in compose, "Docker Compose is missing the metrics table")
    require('allow_origins=["*"]' not in stack, "API Gateway still enables wildcard CORS")
    require('"CORS_ORIGINS": "*"' not in stack, "Lambda still receives wildcard CORS")

    doc_lower = doc.lower()
    for phrase in (
        "amazon cognito",
        "jwt scopes",
        "dynamodb query",
        "incremental metrics",
        "local mode remains unauthenticated",
        "not production-ready",
    ):
        require(phrase in doc_lower, f"P0 documentation missing concept: {phrase}")

    print("P0 production control guardrails passed")


if __name__ == "__main__":
    main()
