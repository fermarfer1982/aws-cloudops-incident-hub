from __future__ import annotations

from typing import cast

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_lambda as lambda_

from .stack import READ_SCOPE, SUMMARIZE_SCOPE, WRITE_SCOPE


def apply_aws_performance_controls(
    stack: Stack,
    *,
    enable_load_test_client: bool = False,
) -> None:
    """Expose measurement identifiers and optionally add an ephemeral M2M client."""

    api = cast(apigwv2.HttpApi, stack.node.find_child("HttpApi"))
    api_function = cast(lambda_.Function, stack.node.find_child("ApiFunction"))
    processor_function = cast(
        lambda_.Function,
        stack.node.find_child("ProcessorFunction"),
    )

    CfnOutput(stack, "ApiId", value=api.api_id)
    CfnOutput(stack, "ApiFunctionName", value=api_function.function_name)
    CfnOutput(stack, "ProcessorFunctionName", value=processor_function.function_name)

    if not enable_load_test_client:
        return

    user_pool = cast(cognito.UserPool, stack.node.find_child("UserPool"))
    web_client = cast(
        cognito.UserPoolClient,
        user_pool.node.find_child("WebClient"),
    )
    resource_server = cast(
        cognito.UserPoolResourceServer,
        user_pool.node.find_child("ApiResourceServer"),
    )
    user_pool_domain = cast(
        cognito.UserPoolDomain,
        user_pool.node.find_child("UserPoolDomain"),
    )

    client = cognito.CfnUserPoolClient(
        stack,
        "LoadTestMachineClient",
        user_pool_id=user_pool.user_pool_id,
        client_name="cloudops-incident-hub-ephemeral-load-test",
        generate_secret=True,
        prevent_user_existence_errors="ENABLED",
        allowed_o_auth_flows=["client_credentials"],
        allowed_o_auth_flows_user_pool_client=True,
        allowed_o_auth_scopes=[READ_SCOPE, WRITE_SCOPE, SUMMARIZE_SCOPE],
        access_token_validity=15,
        token_validity_units=cognito.CfnUserPoolClient.TokenValidityUnitsProperty(
            access_token="minutes"
        ),
    )
    client.add_dependency(
        cast(
            cognito.CfnUserPoolResourceServer,
            resource_server.node.default_child,
        )
    )

    jwt_authorizers = [
        construct
        for construct in stack.node.find_all()
        if isinstance(construct, apigwv2.CfnAuthorizer)
    ]

    if len(jwt_authorizers) != 1:
        raise ValueError(
            "Expected exactly one API Gateway JWT authorizer, "
            f"found {len(jwt_authorizers)}"
        )

    jwt_authorizers[0].add_property_override(
        "JwtConfiguration.Audience",
        [
            web_client.user_pool_client_id,
            client.ref,
        ],
    )

    CfnOutput(stack, "LoadTestClientId", value=client.ref)
    CfnOutput(
        stack,
        "LoadTestTokenUrl",
        value=f"{user_pool_domain.base_url()}/oauth2/token",
    )
    CfnOutput(
        stack,
        "LoadTestTokenValidityMinutes",
        value=str(Duration.minutes(15).to_minutes()),
    )
