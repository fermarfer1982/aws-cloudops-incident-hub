from aws_cdk import App
from aws_cdk.assertions import Match, Template

from cloudops_infra.stack import CloudOpsIncidentHubStack


def get_template() -> Template:
    app = App()
    stack = CloudOpsIncidentHubStack(app, "TestStack", bundle_dependencies=False)
    return Template.from_stack(stack)


def test_expected_serverless_resources_are_created():
    template = get_template()
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.resource_count_is("AWS::Lambda::Function", 2)
    template.resource_count_is("AWS::ApiGatewayV2::Api", 1)
    template.resource_count_is("AWS::Events::EventBus", 1)
    template.resource_count_is("AWS::Events::Rule", 1)
    template.resource_count_is("AWS::SQS::Queue", 2)
    template.resource_count_is("AWS::Lambda::EventSourceMapping", 1)
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 4)


def test_dynamodb_is_on_demand_and_ephemeral():
    template = get_template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "SSESpecification": {"SSEEnabled": True},
        },
    )
    template.has_resource(
        "AWS::DynamoDB::Table",
        {"DeletionPolicy": "Delete", "UpdateReplacePolicy": "Delete"},
    )


def test_lambdas_have_bounded_compute():
    template = get_template()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "ReservedConcurrentExecutions": 2,
            "MemorySize": 256,
            "Runtime": "python3.13",
            "Architectures": ["arm64"],
        },
    )


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


def test_lambda_policy_is_scoped_to_project_resources():
    template = get_template()
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Effect": "Allow",
                                "Action": Match.array_with(
                                    ["dynamodb:GetItem", "dynamodb:PutItem"]
                                ),
                            }
                        )
                    ]
                )
            }
        },
    )
