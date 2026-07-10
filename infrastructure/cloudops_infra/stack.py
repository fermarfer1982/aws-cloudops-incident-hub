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
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as event_targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
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

        event_bus = events.EventBus(
            self,
            "IncidentEventBus",
            event_bus_name="cloudops-incident-hub",
            description="Validated infrastructure incidents awaiting asynchronous processing",
        )
        event_bus.apply_removal_policy(RemovalPolicy.DESTROY)

        processing_dlq = sqs.Queue(
            self,
            "IncidentProcessingDlq",
            queue_name="cloudops-incident-processing-dlq",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.DESTROY,
        )
        processing_queue = sqs.Queue(
            self,
            "IncidentProcessingQueue",
            queue_name="cloudops-incident-processing",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            visibility_timeout=Duration.seconds(60),
            retention_period=Duration.days(1),
            dead_letter_queue=sqs.DeadLetterQueue(
                queue=processing_dlq,
                max_receive_count=3,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        event_rule = events.Rule(
            self,
            "IncidentReceivedRule",
            event_bus=event_bus,
            description="Route validated incident events to the processing queue",
            event_pattern=events.EventPattern(
                source=["cloudops.incident-hub"],
                detail_type=["InfrastructureIncidentReceived"],
            ),
        )
        event_rule.add_target(
            event_targets.SqsQueue(
                processing_queue,
                max_event_age=Duration.hours(1),
                retry_attempts=3,
            )
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

        def backend_code() -> lambda_.Code:
            return lambda_.Code.from_asset(backend_path, bundling=bundling)

        api_log_group = logs.LogGroup(
            self,
            "ApiFunctionLogGroup",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY,
        )
        api_function = lambda_.Function(
            self,
            "ApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="app.main.handler",
            code=backend_code(),
            environment={
                "TABLE_NAME": table.table_name,
                "EVENT_BUS_NAME": event_bus.event_bus_name,
                "EVENT_SOURCE": "cloudops.incident-hub",
                "CORS_ORIGINS": "*",
            },
            timeout=Duration.seconds(10),
            memory_size=256,
            reserved_concurrent_executions=2,
            log_group=api_log_group,
            tracing=lambda_.Tracing.DISABLED,
        )
        table.grant_read_write_data(api_function)
        event_bus.grant_put_events_to(api_function)

        processor_log_group = logs.LogGroup(
            self,
            "ProcessorFunctionLogGroup",
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY,
        )
        processor_function = lambda_.Function(
            self,
            "ProcessorFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="app.processor.handler",
            code=backend_code(),
            environment={"TABLE_NAME": table.table_name},
            timeout=Duration.seconds(15),
            memory_size=256,
            reserved_concurrent_executions=2,
            log_group=processor_log_group,
            tracing=lambda_.Tracing.DISABLED,
        )
        table.grant_read_write_data(processor_function)
        processor_function.add_event_source(
            lambda_event_sources.SqsEventSource(
                processing_queue,
                batch_size=10,
                max_batching_window=Duration.seconds(5),
                report_batch_item_failures=True,
            )
        )

        integration = integrations.HttpLambdaIntegration(
            "ApiIntegration",
            handler=api_function,
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
        CfnOutput(self, "EventBusName", value=event_bus.event_bus_name)
        CfnOutput(self, "ProcessingQueueName", value=processing_queue.queue_name)
        CfnOutput(self, "ProcessingDlqName", value=processing_dlq.queue_name)
