#!/usr/bin/env python3
from aws_cdk import App, Environment, Tags

from cloudops_infra.stack import CloudOpsIncidentHubStack

app = App()
stack = CloudOpsIncidentHubStack(
    app,
    "CloudOpsIncidentHubStack",
    env=Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "eu-west-1",
    ),
    description="Ephemeral zero-cost-minded serverless CloudOps portfolio project",
)

Tags.of(stack).add("Project", "aws-cloudops-incident-hub")
Tags.of(stack).add("Environment", "ephemeral-lab")
Tags.of(stack).add("ManagedBy", "aws-cdk")

app.synth()
