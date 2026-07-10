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
from aws_cdk import aws_cloudwatch as cloudwatch
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

        api_error_alarm = api_function.metric_errors(
            period=Duration.minutes(5),
            statistic="Sum",
        ).create_alarm(
            self,
            "ApiFunctionErrorsAlarm",
            alarm_name="cloudops-api-function-errors",
            alarm_description="The ingestion API Lambda returned one or more errors in five minutes.",
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        processor_error_alarm = processor_function.metric_errors(
            period=Duration.minutes(5),
            statistic="Sum",
        ).create_alarm(
            self,
            "ProcessorFunctionErrorsAlarm",
            alarm_name="cloudops-processor-function-errors",
            alarm_description="The asynchronous incident processor returned an error.",
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        queue_age_alarm = processing_queue.metric_approximate_age_of_oldest_message(
            period=Duration.minutes(5),
            statistic="Maximum",
        ).create_alarm(
            self,
            "ProcessingQueueAgeAlarm",
            alarm_name="cloudops-processing-queue-age",
            alarm_description="The oldest processing message has been waiting for at least five minutes.",
            threshold=300,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        dlq_alarm = processing_dlq.metric_approximate_number_of_messages_visible(
            period=Duration.minutes(1),
            statistic="Maximum",
        ).create_alarm(
            self,
            "ProcessingDlqMessagesAlarm",
            alarm_name="cloudops-processing-dlq-messages",
            alarm_description="At least one event requires manual investigation in the dead-letter queue.",
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        dashboard = cloudwatch.Dashboard(
            self,
            "OperationsDashboard",
            dashboard_name="cloudops-incident-hub-operations",
            start="-PT3H",
        )
        dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown=(
                    "# AWS CloudOps Incident Hub\n"
                    "Operational signals derived exclusively from AWS service metrics. "
                    "No custom metrics are emitted by this laboratory."
                ),
                width=24,
                height=2,
            ),
            cloudwatch.GraphWidget(
                title="Lambda errors and throttles",
                left=[
                    api_function.metric_errors(
                        period=Duration.minutes(5), statistic="Sum", label="API errors"
                    ),
                    processor_function.metric_errors(
                        period=Duration.minutes(5), statistic="Sum", label="Processor errors"
                    ),
                ],
                right=[
                    api_function.metric_throttles(
                        period=Duration.minutes(5), statistic="Sum", label="API throttles"
                    ),
                    processor_function.metric_throttles(
                        period=Duration.minutes(5),
                        statistic="Sum",
                        label="Processor throttles",
                    ),
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Lambda p95 duration",
                left=[
                    api_function.metric_duration(
                        period=Duration.minutes(5), statistic="p95", label="API p95"
                    ),
                    processor_function.metric_duration(
                        period=Duration.minutes(5), statistic="p95", label="Processor p95"
                    ),
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Processing queue backlog",
                left=[
                    processing_queue.metric_approximate_number_of_messages_visible(
                        period=Duration.minutes(5), statistic="Maximum", label="Visible messages"
                    )
                ],
                right=[
                    processing_queue.metric_approximate_age_of_oldest_message(
                        period=Duration.minutes(5), statistic="Maximum", label="Oldest message (s)"
                    )
                ],
                width=12,
            ),
            cloudwatch.SingleValueWidget(
                title="Dead-letter queue",
                metrics=[
                    processing_dlq.metric_approximate_number_of_messages_visible(
                        period=Duration.minutes(1), statistic="Maximum", label="Messages awaiting triage"
                    )
                ],
                width=12,
            ),
            cloudwatch.AlarmWidget(
                title="API errors alarm",
                alarm=api_error_alarm,
                width=6,
            ),
            cloudwatch.AlarmWidget(
                title="Processor errors alarm",
                alarm=processor_error_alarm,
                width=6,
            ),
            cloudwatch.AlarmWidget(
                title="Queue age alarm",
                alarm=queue_age_alarm,
                width=6,
            ),
            cloudwatch.AlarmWidget(
                title="DLQ alarm",
                alarm=dlq_alarm,
                width=6,
            ),
        )

        CfnOutput(self, "ApiUrl", value=api.api_endpoint)
        CfnOutput(self, "TableName", value=table.table_name)
        CfnOutput(self, "EventBusName", value=event_bus.event_bus_name)
        CfnOutput(self, "ProcessingQueueName", value=processing_queue.queue_name)
        CfnOutput(self, "ProcessingDlqName", value=processing_dlq.queue_name)
        CfnOutput(self, "OperationsDashboardName", value=dashboard.dashboard_name)
