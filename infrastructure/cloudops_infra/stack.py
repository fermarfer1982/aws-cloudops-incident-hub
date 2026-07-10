from __future__ import annotations

from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct


class CloudOpsIncidentHubStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        bundle_dependencies: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        table = dynamodb.Table(
            self,
            "IncidentsTable",
            partition_key=dynamodb.Attribute(
                name="incident_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
        )

        backend_path = str(Path(__file__).resolve().parents[2] / "backend")
        bundling = (
            BundlingOptions(
                image=lambda_.Runtime.PYTHON_3_13.bundling_image,
                command=[
                    "bash",
                    "-c",
                    "pip install -r requirements.txt -t /asset-output "
                    "&& cp -r app /asset-output/app",
                ],
            )
            if bundle_dependencies
            else None
        )
        function_code = lambda_.Code.from_asset(backend_path, bundling=bundling)

        log_group = logs.LogGroup(
            self,
            "ApiFunctionLogGroup",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY,
        )

        function = lambda_.Function(
            self,
            "ApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="app.main.handler",
            code=function_code,
            environment={
                "TABLE_NAME": table.table_name,
                "CORS_ORIGINS": "*",
            },
            timeout=Duration.seconds(10),
            memory_size=256,
            reserved_concurrent_executions=2,
            log_group=log_group,
            tracing=lambda_.Tracing.DISABLED,
        )
        table.grant_read_write_data(function)

        integration = integrations.HttpLambdaIntegration(
            "ApiIntegration",
            handler=function,
        )

        api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="cloudops-incident-hub-api",
            description="HTTP API for the CloudOps Incident Hub portfolio project",
            default_integration=integration,
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_headers=["content-type", "authorization"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.PATCH,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_origins=["*"],
                max_age=Duration.hours(1),
            ),
        )

        CfnOutput(self, "ApiUrl", value=api.api_endpoint)
        CfnOutput(self, "TableName", value=table.table_name)
