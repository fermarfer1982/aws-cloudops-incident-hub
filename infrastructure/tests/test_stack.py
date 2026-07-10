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
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::ApiGatewayV2::Api", 1)


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


def test_lambda_has_concurrency_and_short_timeout():
    template = get_template()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "ReservedConcurrentExecutions": 2,
            "Timeout": 10,
            "MemorySize": 256,
            "Runtime": "python3.13",
            "Architectures": ["arm64"],
        },
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


def test_lambda_policy_is_scoped_to_the_table():
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
