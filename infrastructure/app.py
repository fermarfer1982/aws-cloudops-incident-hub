#!/usr/bin/env python3
from __future__ import annotations

from aws_cdk import App, Environment, Tags

from cloudops_infra.aws_performance import apply_aws_performance_controls
from cloudops_infra.performance import expose_pagination_header
from cloudops_infra.reliability import apply_reliability_controls
from cloudops_infra.security import (
    DEFAULT_API_BURST_LIMIT,
    DEFAULT_API_RATE_LIMIT,
    apply_operational_security_controls,
)
from cloudops_infra.stack import (
    DEFAULT_ALLOWED_ORIGINS,
    DEFAULT_CALLBACK_URLS,
    CloudOpsIncidentHubStack,
)


def csv_context(app: App, name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = app.node.try_get_context(name)
    if value is None:
        return default
    if isinstance(value, str):
        result = tuple(item.strip() for item in value.split(",") if item.strip())
    elif isinstance(value, list):
        result = tuple(str(item).strip() for item in value if str(item).strip())
    else:
        raise ValueError(f"CDK context {name} must be a comma-separated string or list")
    if not result:
        raise ValueError(f"CDK context {name} must not be empty")
    return result


def bool_context(app: App, name: str, default: bool = False) -> bool:
    value = app.node.try_get_context(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"CDK context {name} must be a boolean")


def optional_string_context(app: App, name: str) -> str | None:
    value = app.node.try_get_context(name)
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def positive_float_context(app: App, name: str, default: float) -> float:
    value = app.node.try_get_context(name)
    result = default if value is None else float(value)
    if result <= 0:
        raise ValueError(f"CDK context {name} must be greater than zero")
    return result


def positive_int_context(app: App, name: str, default: int) -> int:
    value = app.node.try_get_context(name)
    result = default if value is None else int(value)
    if result <= 0:
        raise ValueError(f"CDK context {name} must be greater than zero")
    return result


app = App()
persistent_environment = bool_context(app, "persistent_environment")
enable_load_test_client = bool_context(app, "enable_load_test_client")
alarm_notification_email = optional_string_context(app, "alarm_notification_email")
api_throttling_rate_limit = positive_float_context(
    app,
    "api_throttling_rate_limit",
    DEFAULT_API_RATE_LIMIT,
)
api_throttling_burst_limit = positive_int_context(
    app,
    "api_throttling_burst_limit",
    DEFAULT_API_BURST_LIMIT,
)

stack = CloudOpsIncidentHubStack(
    app,
    "CloudOpsIncidentHubStack",
    env=Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "eu-west-1",
    ),
    description=(
        "Serverless CloudOps portfolio project with security, reliability and pagination"
    ),
    allowed_origins=csv_context(app, "allowed_origins", DEFAULT_ALLOWED_ORIGINS),
    oauth_callback_urls=csv_context(app, "oauth_callback_urls", DEFAULT_CALLBACK_URLS),
    oauth_logout_urls=csv_context(app, "oauth_logout_urls", DEFAULT_CALLBACK_URLS),
)

apply_operational_security_controls(
    stack,
    api_throttling_rate_limit=api_throttling_rate_limit,
    api_throttling_burst_limit=api_throttling_burst_limit,
)
expose_pagination_header(stack)
apply_reliability_controls(
    stack,
    persistent_environment=persistent_environment,
    alarm_notification_email=alarm_notification_email,
)
apply_aws_performance_controls(
    stack,
    enable_load_test_client=enable_load_test_client,
)

Tags.of(stack).add("Project", "aws-cloudops-incident-hub")
Tags.of(stack).add(
    "Environment",
    "persistent-reference" if persistent_environment else "ephemeral-lab",
)
Tags.of(stack).add("ManagedBy", "aws-cdk")

app.synth()
