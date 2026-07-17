import json
import re

import pytest
from aws_cdk import App
from aws_cdk.assertions import Template

from cloudops_infra.reliability import apply_reliability_controls
from cloudops_infra.stack import CloudOpsIncidentHubStack


GENAI_FUNCTION_NAME = "cloudops-genai-summary-function"
GENAI_ROUTE_KEY = "POST /incidents/{incident_id}/ai-summary"
SUMMARIZE_SCOPE = "cloudops-incident-hub/incidents.summarize"
ACCOUNT_ID_PATTERN = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")
ACCOUNT_ARN_PATTERN = re.compile(
    r"arn:(?:aws|aws-us-gov|aws-cn):[^:]+:[^:]*:[0-9]{12}:"
)
ACCOUNT_SENSITIVE_KEYS = {
    "account",
    "accountid",
    "awsaccountid",
    "allowedaccountids",
    "sourceaccount",
    "aws:sourceaccount",
    "assumerolepolicydocument",
    "policydocument",
    "principal",
    "resource",
    "condition",
    "outputs",
}


def _safe_path_component(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "?", str(value))


def _strings_in(value: object, path: tuple[str, ...]):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key in sorted(value, key=str):
            yield from _strings_in(
                value[key], (*path, _safe_path_component(key))
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings_in(item, (*path, str(index)))


def literal_account_id_paths(template: dict) -> list[str]:
    """Return deterministic paths containing literal AWS account identifiers."""
    matches: set[str] = set()

    for path, value in _strings_in(template, ("template",)):
        if ACCOUNT_ARN_PATTERN.search(value):
            matches.add(".".join(path))

    def inspect_sensitive(value: object, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key in sorted(value, key=str):
                key_path = (*path, _safe_path_component(key))
                child = value[key]
                if str(key).lower() in ACCOUNT_SENSITIVE_KEYS:
                    for string_path, text in _strings_in(child, key_path):
                        if ACCOUNT_ID_PATTERN.search(text):
                            matches.add(".".join(string_path))
                inspect_sensitive(child, key_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                inspect_sensitive(item, (*path, str(index)))

    inspect_sensitive(template, ("template",))
    return sorted(matches)


def synthesize(*, persistent_environment: bool = False) -> dict:
    app = App()
    stack = CloudOpsIncidentHubStack(app, "TestStack", bundle_dependencies=False)
    if persistent_environment:
        apply_reliability_controls(stack, persistent_environment=True)
    return Template.from_stack(stack).to_json()


def resources_of_type(template: dict, resource_type: str) -> dict[str, dict]:
    return {
        logical_id: resource
        for logical_id, resource in template["Resources"].items()
        if resource["Type"] == resource_type
    }


def genai_function(template: dict) -> tuple[str, dict]:
    functions = resources_of_type(template, "AWS::Lambda::Function")
    matches = [
        (logical_id, resource)
        for logical_id, resource in functions.items()
        if resource["Properties"].get("FunctionName") == GENAI_FUNCTION_NAME
    ]
    assert len(matches) == 1
    return matches[0]


def genai_role_and_policies(template: dict) -> tuple[str, dict, list[dict]]:
    _, function = genai_function(template)
    role_logical_id = function["Properties"]["Role"]["Fn::GetAtt"][0]
    role = template["Resources"][role_logical_id]
    policies = [
        resource
        for resource in resources_of_type(template, "AWS::IAM::Policy").values()
        if {"Ref": role_logical_id} in resource["Properties"].get("Roles", [])
    ]
    return role_logical_id, role, policies


def policy_statements(policies: list[dict]) -> list[dict]:
    return [
        statement
        for policy in policies
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]


def actions_from(statements: list[dict]) -> set[str]:
    actions: set[str] = set()
    for statement in statements:
        value = statement["Action"]
        actions.update([value] if isinstance(value, str) else value)
    return actions


def test_dedicated_genai_lambda_has_bounded_closed_configuration():
    template = synthesize()
    functions = resources_of_type(template, "AWS::Lambda::Function")
    logical_id, function = genai_function(template)
    properties = function["Properties"]

    assert len(functions) == 3
    assert properties["Runtime"] == "python3.13"
    assert properties["Architectures"] == ["arm64"]
    assert properties["Handler"] == "app.main.handler"
    assert properties["MemorySize"] == 256
    assert properties["Timeout"] == 15
    assert properties["ReservedConcurrentExecutions"] == 1
    assert "TracingConfig" not in properties
    assert "DeadLetterConfig" not in properties
    assert "EventInvokeConfig" not in properties

    api_function = next(
        resource
        for resource in functions.values()
        if resource["Properties"].get("Handler") == "app.main.handler"
        and resource["Properties"].get("FunctionName") != GENAI_FUNCTION_NAME
    )
    assert properties["Code"] == api_function["Properties"]["Code"]
    assert logical_id != next(
        identifier
        for identifier, resource in functions.items()
        if resource is api_function
    )


def test_genai_environment_is_exactly_closed_and_uses_table_references():
    template = synthesize()
    _, function = genai_function(template)
    variables = function["Properties"]["Environment"]["Variables"]

    expected_literals = {
        "AI_SUMMARY_ENABLED": "false",
        "AI_SUMMARY_PROVIDER": "disabled",
        "AI_SUMMARY_PROMPT_VERSION": "incident-summary-v1",
        "AI_SUMMARY_MAX_CONTEXT_CHARS": "8000",
        "AI_SUMMARY_MAX_OUTPUT_CHARS": "6000",
        "AI_SUMMARY_MAX_TOKENS": "800",
        "AI_SUMMARY_TEMPERATURE": "0.0",
        "AI_SUMMARY_CONNECT_TIMEOUT_SECONDS": "3",
        "AI_SUMMARY_READ_TIMEOUT_SECONDS": "30",
        "AI_SUMMARY_MAX_ATTEMPTS": "2",
    }
    for name, value in expected_literals.items():
        assert variables[name] == value

    assert set(variables) == {
        "TABLE_NAME",
        "METRICS_TABLE_NAME",
        "CORS_ORIGINS",
        *expected_literals,
    }
    assert variables["TABLE_NAME"] == {"Ref": "IncidentsTable307EBBA6"}
    assert variables["METRICS_TABLE_NAME"] == {"Ref": "IncidentMetricsTable3E6CD2E6"}
    assert variables["CORS_ORIGINS"]
    assert "EVENT_BUS_NAME" not in variables
    assert "AI_SUMMARY_MODEL_ID" not in variables
    assert "AI_SUMMARY_ALLOWED_MODEL_IDS" not in variables
    assert not any("CREDENTIAL" in name or "ACCESS_KEY" in name for name in variables)
    assert not any("ENDPOINT" in name for name in variables)


def test_cognito_preserves_existing_scopes_and_adds_summarize_to_web_client():
    template = synthesize()
    resource_server = next(
        resource["Properties"]
        for resource in resources_of_type(
            template, "AWS::Cognito::UserPoolResourceServer"
        ).values()
    )
    assert {scope["ScopeName"] for scope in resource_server["Scopes"]} == {
        "incidents.read",
        "incidents.write",
        "incidents.manage",
        "incidents.summarize",
    }

    client = next(
        resource["Properties"]
        for resource in resources_of_type(
            template, "AWS::Cognito::UserPoolClient"
        ).values()
    )
    rendered_scopes = json.dumps(client["AllowedOAuthScopes"], sort_keys=True)
    for scope in (
        "incidents.read",
        "incidents.write",
        "incidents.manage",
        "incidents.summarize",
    ):
        assert f"/{scope}" in rendered_scopes


def test_ai_route_uses_dedicated_integration_jwt_and_summarize_scope():
    template = synthesize()
    genai_logical_id, _ = genai_function(template)
    routes = resources_of_type(template, "AWS::ApiGatewayV2::Route")
    integrations = resources_of_type(template, "AWS::ApiGatewayV2::Integration")

    matching_routes = [
        resource["Properties"]
        for resource in routes.values()
        if resource["Properties"]["RouteKey"] == GENAI_ROUTE_KEY
    ]
    assert len(matching_routes) == 1
    route = matching_routes[0]
    assert route["AuthorizationType"] == "JWT"
    assert route["AuthorizationScopes"] == [SUMMARIZE_SCOPE]
    assert "AuthorizerId" in route

    integration_logical_id = route["Target"]["Fn::Join"][1][1]["Ref"]
    integration = integrations[integration_logical_id]["Properties"]
    assert integration["IntegrationType"] == "AWS_PROXY"
    assert integration["PayloadFormatVersion"] == "2.0"
    assert integration["IntegrationUri"] == {
        "Fn::GetAtt": [genai_logical_id, "Arn"]
    }

    assert len(resources_of_type(template, "AWS::ApiGatewayV2::Api")) == 1
    public_routes = [
        route["Properties"]["RouteKey"]
        for route in routes.values()
        if route["Properties"].get("AuthorizationType", "NONE") == "NONE"
    ]
    assert public_routes == ["GET /health"]


def test_genai_role_is_independent_and_has_only_own_logs_and_get_item():
    template = synthesize()
    role_logical_id, role, policies = genai_role_and_policies(template)
    statements = policy_statements(policies)
    actions = actions_from(statements)

    assert len(policies) == 1
    assert "ManagedPolicyArns" not in role["Properties"]
    assert actions == {
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "dynamodb:GetItem",
    }
    dynamodb_statement = next(
        statement for statement in statements if statement["Action"] == "dynamodb:GetItem"
    )
    assert dynamodb_statement["Resource"] == {
        "Fn::GetAtt": ["IncidentsTable307EBBA6", "Arn"]
    }

    logs_statement = next(
        statement
        for statement in statements
        if statement["Action"] == ["logs:CreateLogStream", "logs:PutLogEvents"]
    )
    assert "GenAiSummaryFunctionLogGroup" in json.dumps(logs_statement["Resource"])
    assert "IncidentMetricsTable" not in json.dumps(statements)
    assert "/index/" not in json.dumps(statements)
    assert role_logical_id not in {
        resource["Properties"]["Role"]["Fn::GetAtt"][0]
        for _, resource in resources_of_type(template, "AWS::Lambda::Function").items()
        if resource["Properties"].get("FunctionName") != GENAI_FUNCTION_NAME
    }


def test_genai_role_has_no_forbidden_service_or_write_permissions():
    template = synthesize()
    _, _, policies = genai_role_and_policies(template)
    actions = {action.lower() for action in actions_from(policy_statements(policies))}
    forbidden = {
        "dynamodb:batchgetitem",
        "dynamodb:query",
        "dynamodb:scan",
        "dynamodb:conditioncheckitem",
        "dynamodb:putitem",
        "dynamodb:updateitem",
        "dynamodb:deleteitem",
        "dynamodb:batchwriteitem",
        "cloudwatch:putmetricdata",
    }
    assert actions.isdisjoint(forbidden)
    assert not any(
        action.startswith(
            (
                "bedrock:",
                "events:",
                "sqs:",
                "sns:",
                "s3:",
                "secretsmanager:",
                "ssm:",
                "kms:",
            )
        )
        for action in actions
    )
    assert not any("*" in action for action in actions)


def test_genai_logs_retention_alarms_and_native_dashboard_metrics():
    template = synthesize()
    log_groups = resources_of_type(template, "AWS::Logs::LogGroup")
    genai_logs = [
        resource
        for resource in log_groups.values()
        if resource["Properties"].get("LogGroupName")
        == "/aws/lambda/cloudops-genai-summary-function"
    ]
    assert len(genai_logs) == 1
    assert genai_logs[0]["Properties"]["RetentionInDays"] == 1

    alarms = [
        resource["Properties"]
        for resource in resources_of_type(template, "AWS::CloudWatch::Alarm").values()
        if resource["Properties"].get("AlarmName", "").startswith(
            "cloudops-genai-summary-"
        )
    ]
    assert {alarm["AlarmName"] for alarm in alarms} == {
        "cloudops-genai-summary-errors",
        "cloudops-genai-summary-throttles",
    }
    assert {alarm["MetricName"] for alarm in alarms} == {"Errors", "Throttles"}
    assert all(alarm["Namespace"] == "AWS/Lambda" for alarm in alarms)
    assert all(alarm["Period"] == 300 for alarm in alarms)
    assert all(alarm["EvaluationPeriods"] == 1 for alarm in alarms)
    assert all(alarm["TreatMissingData"] == "notBreaching" for alarm in alarms)

    dashboard = next(
        resource["Properties"]
        for resource in resources_of_type(template, "AWS::CloudWatch::Dashboard").values()
    )
    rendered_dashboard = json.dumps(dashboard, sort_keys=True)
    for metric in (
        "Invocations",
        "Errors",
        "Duration",
        "Throttles",
        "ConcurrentExecutions",
    ):
        assert metric in rendered_dashboard
    assert "GenAiSummaryFunction" in rendered_dashboard
    assert "AiSummaryInputTokens" not in rendered_dashboard
    assert "EstimatedCost" not in rendered_dashboard


def test_persistent_mode_retains_genai_logs_for_thirty_days():
    template = synthesize(persistent_environment=True)
    genai_log_group = next(
        resource
        for resource in resources_of_type(template, "AWS::Logs::LogGroup").values()
        if resource["Properties"].get("LogGroupName")
        == "/aws/lambda/cloudops-genai-summary-function"
    )
    assert genai_log_group["Properties"]["RetentionInDays"] == 30
    assert genai_log_group["DeletionPolicy"] == "Retain"
    assert genai_log_group["UpdateReplacePolicy"] == "Retain"


def test_template_has_no_bedrock_configuration_credentials_or_sensitive_outputs():
    template = synthesize()
    rendered = json.dumps(template, sort_keys=True)
    lower = rendered.lower()

    for forbidden in (
        "bedrock:",
        "invokemodel",
        "conversestream",
        "applyguardrail",
        "ai_summary_model_id",
        "ai_summary_allowed_model_ids",
        "inference profile",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "secretsmanager:",
        "cloudwatch:putmetricdata",
    ):
        assert forbidden not in lower
    assert "arn:aws:bedrock" not in lower
    assert literal_account_id_paths(template) == []

    outputs = template.get("Outputs", {})
    forbidden_output_parts = ("rolearn", "tablearn", "model", "inference", "loggrouparn")
    assert not any(
        part in output_name.lower()
        for output_name in outputs
        for part in forbidden_output_parts
    )


def test_synthesized_template_is_deterministic_without_genai_context():
    assert synthesize() == synthesize()


def test_account_detection_ignores_opaque_asset_and_nonsensitive_values():
    template = synthesize()
    template["Resources"]["SyntheticAsset"] = {
        "Type": "Custom::SyntheticAsset",
        "Properties": {
            "S3Key": "asset.123456789012abcdef.zip",
            "DelimitedS3Key": "asset.123456789012.zip",
            "Filename": "report-123456789012.json",
            "OpaqueValue": "123456789012",
            "Checksum": "sha256-123456789012-deadbeef",
        },
    }
    template["Resources"]["Synthetic123456789012Asset"] = {
        "Type": "Custom::SyntheticAsset"
    }

    assert literal_account_id_paths(template) == []


@pytest.mark.parametrize(
    ("fragment", "expected_path"),
    [
        (
            {
                "Principal": {
                    "AWS": "arn:aws:iam::123456789012:root"
                }
            },
            "Principal.AWS",
        ),
        (
            {
                "Resource": (
                    "arn:aws:dynamodb:eu-west-1:123456789012:table/example"
                )
            },
            "Resource",
        ),
        (
            {"Condition": {"StringEquals": {"aws:SourceAccount": "123456789012"}}},
            "Condition.StringEquals.aws:SourceAccount",
        ),
        ({"AccountId": "123456789012"}, "AccountId"),
        ({"AWSAccountId": "123456789012"}, "AWSAccountId"),
        ({"AllowedAccountIds": ["123456789012"]}, "AllowedAccountIds.0"),
        (
            {"Outputs": {"AccountId": {"Value": "123456789012"}}},
            "Outputs.AccountId.Value",
        ),
        (
            {
                "Opaque": (
                    "arn:aws:lambda:eu-west-1:123456789012:function:example"
                )
            },
            "Opaque",
        ),
        (
            {"Principal": "arn:aws-us-gov:iam::123456789012:role/example"},
            "Principal",
        ),
    ],
)
def test_account_detection_finds_literals_in_sensitive_surfaces(
    fragment: dict, expected_path: str
):
    paths = literal_account_id_paths(fragment)

    assert any(path.endswith(expected_path) for path in paths), paths


@pytest.mark.parametrize(
    "fragment",
    [
        {"Value": "${AWS::AccountId}"},
        {"Value": {"Ref": "AWS::AccountId"}},
        {
            "Value": {
                "Fn::Sub": (
                    "arn:${AWS::Partition}:iam::${AWS::AccountId}:role/example"
                )
            }
        },
        {"Resource": {"Fn::GetAtt": ["ExampleRole", "Arn"]}},
        {"Resource": {"Fn::Join": ["", [{"Ref": "ExampleArn"}]]}},
    ],
)
def test_account_detection_allows_pseudoparameters_and_intrinsics(fragment: dict):
    assert literal_account_id_paths(fragment) == []
