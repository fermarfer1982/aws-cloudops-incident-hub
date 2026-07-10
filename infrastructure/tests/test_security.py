import pytest
from aws_cdk import App
from aws_cdk.assertions import Template

from cloudops_infra.security import apply_operational_security_controls
from cloudops_infra.stack import CloudOpsIncidentHubStack


def get_secured_template(
    *,
    rate_limit: float = 10.0,
    burst_limit: int = 20,
) -> Template:
    app = App()
    stack = CloudOpsIncidentHubStack(app, "SecurityTestStack", bundle_dependencies=False)
    apply_operational_security_controls(
        stack,
        api_throttling_rate_limit=rate_limit,
        api_throttling_burst_limit=burst_limit,
    )
    return Template.from_stack(stack)


def test_default_stage_has_explicit_throttling_limits():
    get_secured_template().has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {
            "StageName": "$default",
            "DefaultRouteSettings": {
                "ThrottlingRateLimit": 10,
                "ThrottlingBurstLimit": 20,
            },
        },
    )


def test_throttling_limits_are_configurable():
    get_secured_template(rate_limit=25.5, burst_limit=50).has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {
            "DefaultRouteSettings": {
                "ThrottlingRateLimit": 25.5,
                "ThrottlingBurstLimit": 50,
            }
        },
    )


@pytest.mark.parametrize(
    ("rate_limit", "burst_limit"),
    [
        (0.0, 20),
        (-1.0, 20),
        (10.0, 0),
        (10.0, -1),
    ],
)
def test_invalid_throttling_limits_are_rejected(rate_limit: float, burst_limit: int):
    app = App()
    stack = CloudOpsIncidentHubStack(app, "InvalidSecurityStack", bundle_dependencies=False)

    with pytest.raises(ValueError):
        apply_operational_security_controls(
            stack,
            api_throttling_rate_limit=rate_limit,
            api_throttling_burst_limit=burst_limit,
        )
