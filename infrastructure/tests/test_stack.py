from aws_cdk import App
from aws_cdk.assertions import Match, Template

from cloudops_infra.stack import (
    CloudOpsIncidentHubStack,
    lambda_bundle_command,
)


def get_template() -> Template:
    app = App()
    stack = CloudOpsIncidentHubStack(app, "TestStack", bundle_dependencies=False)
    return Template.from_stack(stack)


def test_lambda_bundle_targets_arm64_python313():
    command = " ".join(lambda_bundle_command())

    assert "--platform manylinux2014_aarch64" in command
    assert "--implementation cp" in command
    assert "--python-version 3.13" in command
    assert "--only-binary=:all:" in command
    assert "--no-compile" in command
    assert "--target /asset-output" in command


def test_expected_serverless_resources_are_created():
    template = get_template()
    template.resource_count_is("AWS::DynamoDB::Table", 2)
    template.resource_count_is("AWS::Lambda::Function", 3)
    template.resource_count_is("AWS::ApiGatewayV2::Api", 1)
    template.resource_count_is("AWS::ApiGatewayV2::Authorizer", 1)
    template.resource_count_is("AWS::ApiGatewayV2::Route", 6)
    template.resource_count_is("AWS::Cognito::UserPool", 1)
    template.resource_count_is("AWS::Cognito::UserPoolClient", 1)
    template.resource_count_is("AWS::Cognito::UserPoolResourceServer", 1)
    template.resource_count_is("AWS::Cognito::UserPoolDomain", 1)
    template.resource_count_is("AWS::Events::EventBus", 1)
    template.resource_count_is("AWS::Events::Rule", 1)
    template.resource_count_is("AWS::SQS::Queue", 2)
    template.resource_count_is("AWS::Lambda::EventSourceMapping", 1)
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 6)


def test_incident_table_uses_queryable_access_patterns():
    resources = get_template().to_json()["Resources"]
    incident_tables = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::DynamoDB::Table"
        and resource["Properties"].get("TableName") == "cloudops-incidents"
    ]
    assert len(incident_tables) == 1
    table = incident_tables[0]
    assert table["BillingMode"] == "PAY_PER_REQUEST"
    assert table["SSESpecification"] == {"SSEEnabled": True}
    assert {index["IndexName"] for index in table["GlobalSecondaryIndexes"]} == {
        "incidents-by-time",
        "incidents-by-site",
        "incidents-by-status",
        "incidents-by-severity",
    }
    assert all(
        index["Projection"] == {"ProjectionType": "ALL"}
        for index in table["GlobalSecondaryIndexes"]
    )


def test_metrics_table_has_group_and_name_key():
    get_template().has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "cloudops-incident-metrics",
            "BillingMode": "PAY_PER_REQUEST",
            "KeySchema": [
                {"AttributeName": "metric_group", "KeyType": "HASH"},
                {"AttributeName": "metric_name", "KeyType": "RANGE"},
            ],
        },
    )


def test_dynamodb_tables_are_ephemeral():
    resources = get_template().to_json()["Resources"]
    tables = [
        resource
        for resource in resources.values()
        if resource["Type"] == "AWS::DynamoDB::Table"
    ]
    assert len(tables) == 2
    assert all(table["DeletionPolicy"] == "Delete" for table in tables)
    assert all(table["UpdateReplacePolicy"] == "Delete" for table in tables)


def test_lambdas_have_bounded_compute_without_reserved_concurrency():
    resources = get_template().to_json()["Resources"]
    functions = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Lambda::Function"
    ]

    assert len(functions) == 3

    for function in functions:
        assert function["MemorySize"] == 256
        assert function["Runtime"] == "python3.13"
        assert function["Architectures"] == ["arm64"]

        variables = function["Environment"]["Variables"]
        assert "TABLE_NAME" in variables
        assert "METRICS_TABLE_NAME" in variables

        assert "ReservedConcurrentExecutions" not in function


def test_processing_queue_has_encryption_and_dlq():
    template = get_template()
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "SqsManagedSseEnabled": True,
            "VisibilityTimeout": 60,
            "MessageRetentionPeriod": 86400,
            "RedrivePolicy": {
                "deadLetterTargetArn": Match.any_value(),
                "maxReceiveCount": 3,
            },
        },
    )


def test_sqs_mapping_reports_partial_batch_failures():
    template = get_template()
    template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {
            "BatchSize": 10,
            "MaximumBatchingWindowInSeconds": 5,
            "ScalingConfig": {"MaximumConcurrency": 2},
            "FunctionResponseTypes": ["ReportBatchItemFailures"],
        },
    )


def test_eventbridge_rule_filters_incident_events():
    template = get_template()
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": {
                "source": ["cloudops.incident-hub"],
                "detail-type": ["InfrastructureIncidentReceived"],
            },
        },
    )


def test_cognito_resource_server_defines_route_scopes():
    get_template().has_resource_properties(
        "AWS::Cognito::UserPoolResourceServer",
        {
            "Identifier": "cloudops-incident-hub",
            "Scopes": Match.array_with(
                [
                    Match.object_like({"ScopeName": "incidents.read"}),
                    Match.object_like({"ScopeName": "incidents.write"}),
                    Match.object_like({"ScopeName": "incidents.manage"}),
                    Match.object_like({"ScopeName": "incidents.summarize"}),
                ]
            ),
        },
    )


def test_only_health_route_is_public_and_other_routes_require_jwt_scopes():
    resources = get_template().to_json()["Resources"]
    routes = {
        resource["Properties"]["RouteKey"]: resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::ApiGatewayV2::Route"
    }

    assert routes["GET /health"].get("AuthorizationType", "NONE") == "NONE"
    expected_scopes = {
        "POST /events": ["cloudops-incident-hub/incidents.write"],
        "GET /events": ["cloudops-incident-hub/incidents.read"],
        "PATCH /events/{incident_id}/status": [
            "cloudops-incident-hub/incidents.manage"
        ],
        "GET /metrics": ["cloudops-incident-hub/incidents.read"],
        "POST /incidents/{incident_id}/ai-summary": [
            "cloudops-incident-hub/incidents.summarize"
        ],
    }
    for route_key, scopes in expected_scopes.items():
        assert routes[route_key]["AuthorizationType"] == "JWT"
        assert routes[route_key]["AuthorizationScopes"] == scopes
        assert "AuthorizerId" in routes[route_key]


def test_cors_uses_an_explicit_allowlist():
    resources = get_template().to_json()["Resources"]
    api = next(
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::ApiGatewayV2::Api"
    )
    origins = api["CorsConfiguration"]["AllowOrigins"]
    assert origins
    assert "*" not in origins
    assert "https://fermarfer1982.github.io" in origins


def test_operational_alarms_are_named_and_ignore_missing_data():
    resources = get_template().to_json()["Resources"]
    alarms = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    ]

    assert {alarm["AlarmName"] for alarm in alarms} == {
        "cloudops-api-function-errors",
        "cloudops-processor-function-errors",
        "cloudops-genai-summary-errors",
        "cloudops-genai-summary-throttles",
        "cloudops-processing-queue-age",
        "cloudops-processing-dlq-messages",
    }
    assert all(alarm["TreatMissingData"] == "notBreaching" for alarm in alarms)
    assert all(not alarm.get("AlarmActions") for alarm in alarms)


def test_dashboard_is_named():
    get_template().has_resource_properties(
        "AWS::CloudWatch::Dashboard",
        {"DashboardName": "cloudops-incident-hub-operations"},
    )


def test_no_known_high_cost_resources_exist():
    template = get_template().to_json()
    resources = template.get("Resources", {})
    forbidden = {
        "AWS::EC2::NatGateway",
        "AWS::EC2::Instance",
        "AWS::RDS::DBInstance",
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::EKS::Cluster",
        "AWS::OpenSearchService::Domain",
    }
    found = {
        resource["Type"]
        for resource in resources.values()
        if resource.get("Type") in forbidden
    }
    assert found == set()


def test_lambda_policies_allow_required_dynamodb_actions_but_not_scan():
    resources = get_template().to_json()["Resources"]
    statements = []
    for resource in resources.values():
        if resource["Type"] != "AWS::IAM::Policy":
            continue
        statements.extend(resource["Properties"]["PolicyDocument"]["Statement"])

    actions = set()
    for statement in statements:
        action = statement.get("Action", [])
        if isinstance(action, str):
            actions.add(action)
        else:
            actions.update(action)

    assert "dynamodb:GetItem" in actions
    assert "dynamodb:PutItem" in actions
    assert "dynamodb:Query" in actions
    assert "dynamodb:UpdateItem" in actions
    assert "dynamodb:TransactWriteItems" not in actions
    assert "dynamodb:Scan" not in actions
