#!/usr/bin/env python3
from __future__ import annotations

from aws_cdk import App, Environment, Tags

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


app = App()
stack = CloudOpsIncidentHubStack(
    app,
    "CloudOpsIncidentHubStack",
    env=Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "eu-west-1",
    ),
    description="Ephemeral serverless CloudOps portfolio project with P0 controls",
    allowed_origins=csv_context(app, "allowed_origins", DEFAULT_ALLOWED_ORIGINS),
    oauth_callback_urls=csv_context(app, "oauth_callback_urls", DEFAULT_CALLBACK_URLS),
    oauth_logout_urls=csv_context(app, "oauth_logout_urls", DEFAULT_CALLBACK_URLS),
)

Tags.of(stack).add("Project", "aws-cloudops-incident-hub")
Tags.of(stack).add("Environment", "ephemeral-lab")
Tags.of(stack).add("ManagedBy", "aws-cdk")

app.synth()
