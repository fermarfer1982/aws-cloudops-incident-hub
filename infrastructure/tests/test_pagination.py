from aws_cdk import App
from aws_cdk.assertions import Template

from cloudops_infra.performance import expose_pagination_header
from cloudops_infra.stack import CloudOpsIncidentHubStack


def test_api_cors_exposes_continuation_token_header():
    app = App()
    stack = CloudOpsIncidentHubStack(app, "PaginationStack", bundle_dependencies=False)

    expose_pagination_header(stack)

    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Api",
        {
            "CorsConfiguration": {
                "ExposeHeaders": ["X-Next-Token"],
            }
        },
    )
