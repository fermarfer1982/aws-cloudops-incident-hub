from aws_cdk import App
from aws_cdk.assertions import Template

from cloudops_infra.aws_performance import apply_aws_performance_controls
from cloudops_infra.stack import CloudOpsIncidentHubStack


def synthesize(*, enable_load_test_client: bool) -> dict:
    app = App()
    stack = CloudOpsIncidentHubStack(
        app,
        "TestStack",
        bundle_dependencies=False,
    )
    apply_aws_performance_controls(
        stack,
        enable_load_test_client=enable_load_test_client,
    )
    return Template.from_stack(stack).to_json()


def test_default_reference_does_not_create_machine_client():
    resources = synthesize(enable_load_test_client=False)["Resources"]
    clients = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Cognito::UserPoolClient"
    ]

    authorizer = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::ApiGatewayV2::Authorizer"
    )

    assert len(clients) == 1
    assert all(client.get("GenerateSecret") is not True for client in clients)
    assert len(authorizer["JwtConfiguration"]["Audience"]) == 1


def test_ephemeral_performance_profile_creates_scoped_machine_client():
    resources = synthesize(enable_load_test_client=True)["Resources"]
    clients = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Cognito::UserPoolClient"
    ]
    machine_client = next(
        client
        for client in clients
        if client.get("ClientName")
        == "cloudops-incident-hub-ephemeral-load-test"
    )

    assert len(clients) == 2
    assert machine_client["GenerateSecret"] is True
    assert machine_client["AllowedOAuthFlows"] == ["client_credentials"]
    assert machine_client["AllowedOAuthFlowsUserPoolClient"] is True
    assert set(machine_client["AllowedOAuthScopes"]) == {
        "cloudops-incident-hub/incidents.read",
        "cloudops-incident-hub/incidents.write",
    }
    assert machine_client["AccessTokenValidity"] == 15
    assert machine_client["TokenValidityUnits"] == {
        "AccessToken": "minutes"
    }


def test_machine_client_is_included_in_jwt_authorizer_audience():
    resources = synthesize(enable_load_test_client=True)["Resources"]

    machine_client_logical_id = next(
        logical_id
        for logical_id, resource in resources.items()
        if resource["Type"] == "AWS::Cognito::UserPoolClient"
        and resource["Properties"].get("ClientName")
        == "cloudops-incident-hub-ephemeral-load-test"
    )

    authorizer = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::ApiGatewayV2::Authorizer"
    )

    audiences = authorizer["JwtConfiguration"]["Audience"]

    assert len(audiences) == 2
    assert {"Ref": machine_client_logical_id} in audiences


def test_performance_measurement_outputs_are_exposed():
    outputs = synthesize(enable_load_test_client=True)["Outputs"]

    assert "ApiId" in outputs
    assert "ApiFunctionName" in outputs
    assert "ProcessorFunctionName" in outputs
    assert "LoadTestClientId" in outputs
    assert "LoadTestTokenUrl" in outputs
