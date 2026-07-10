from __future__ import annotations

from typing import cast

from aws_cdk import CfnOutput, Stack, Tags
from aws_cdk import aws_apigatewayv2 as apigwv2

DEFAULT_API_RATE_LIMIT = 10.0
DEFAULT_API_BURST_LIMIT = 20


def apply_operational_security_controls(
    stack: Stack,
    *,
    api_throttling_rate_limit: float = DEFAULT_API_RATE_LIMIT,
    api_throttling_burst_limit: int = DEFAULT_API_BURST_LIMIT,
) -> None:
    """Apply explicit HTTP API throttling without adding persistent resources."""

    if api_throttling_rate_limit <= 0:
        raise ValueError("api_throttling_rate_limit must be greater than zero")
    if api_throttling_burst_limit <= 0:
        raise ValueError("api_throttling_burst_limit must be greater than zero")

    api = cast(apigwv2.HttpApi, stack.node.find_child("HttpApi"))
    default_stage = api.default_stage
    if default_stage is None:
        raise RuntimeError("The HTTP API must define a default stage")

    cfn_stage = cast(apigwv2.CfnStage, default_stage.node.default_child)
    cfn_stage.default_route_settings = apigwv2.CfnStage.RouteSettingsProperty(
        throttling_rate_limit=api_throttling_rate_limit,
        throttling_burst_limit=api_throttling_burst_limit,
    )

    Tags.of(stack).add("ApiProtection", "jwt-and-throttling")

    CfnOutput(
        stack,
        "ApiThrottlingRateLimit",
        value=str(api_throttling_rate_limit),
        description="Default API Gateway requests-per-second throttling limit",
    )
    CfnOutput(
        stack,
        "ApiThrottlingBurstLimit",
        value=str(api_throttling_burst_limit),
        description="Default API Gateway burst throttling limit",
    )
