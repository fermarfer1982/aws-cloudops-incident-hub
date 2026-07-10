from __future__ import annotations

from typing import cast

from aws_cdk import Stack
from aws_cdk import aws_apigatewayv2 as apigwv2


def expose_pagination_header(stack: Stack) -> None:
    """Allow browser clients to read the API continuation-token response header."""

    api = cast(apigwv2.HttpApi, stack.node.find_child("HttpApi"))
    cfn_api = cast(apigwv2.CfnApi, api.node.default_child)
    cfn_api.add_property_override(
        "CorsConfiguration.ExposeHeaders",
        ["X-Next-Token"],
    )
