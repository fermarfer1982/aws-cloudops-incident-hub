from __future__ import annotations

from typing import cast

from aws_cdk import CfnOutput, RemovalPolicy, Stack, Tags
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions

TABLE_IDS = ("IncidentsTable", "IncidentMetricsTable")
LOG_GROUP_IDS = ("ApiFunctionLogGroup", "ProcessorFunctionLogGroup")
ALARM_IDS = (
    "ApiFunctionErrorsAlarm",
    "ProcessorFunctionErrorsAlarm",
    "ProcessingQueueAgeAlarm",
    "ProcessingDlqMessagesAlarm",
)


def apply_reliability_controls(
    stack: Stack,
    *,
    persistent_environment: bool = False,
    alarm_notification_email: str | None = None,
) -> None:
    """Apply P1 controls without changing the zero-cost ephemeral default.

    Persistent environments retain both DynamoDB tables, enable point-in-time
    recovery and retain operational logs for 30 days. Alarm routing is opt-in
    because an email subscription must be explicitly confirmed by its owner.
    """

    if alarm_notification_email is not None:
        alarm_notification_email = alarm_notification_email.strip()
        if not alarm_notification_email or "@" not in alarm_notification_email:
            raise ValueError("alarm_notification_email must be a valid non-empty email")

    if persistent_environment:
        for construct_id in TABLE_IDS:
            table = cast(dynamodb.Table, stack.node.find_child(construct_id))
            table.apply_removal_policy(RemovalPolicy.RETAIN)
            cfn_table = cast(dynamodb.CfnTable, table.node.default_child)
            cfn_table.point_in_time_recovery_specification = (
                dynamodb.CfnTable.PointInTimeRecoverySpecificationProperty(
                    point_in_time_recovery_enabled=True
                )
            )

        for construct_id in LOG_GROUP_IDS:
            log_group = cast(logs.LogGroup, stack.node.find_child(construct_id))
            log_group.apply_removal_policy(RemovalPolicy.RETAIN)
            cfn_log_group = cast(logs.CfnLogGroup, log_group.node.default_child)
            cfn_log_group.retention_in_days = 30

        Tags.of(stack).add("DataProtection", "pitr-retain")
    else:
        Tags.of(stack).add("DataProtection", "ephemeral-destroy")

    CfnOutput(
        stack,
        "DataProtectionMode",
        value="persistent-pitr-retain" if persistent_environment else "ephemeral-destroy",
        description="DynamoDB and log retention mode selected for this deployment",
    )

    if alarm_notification_email:
        alarm_topic = sns.Topic(
            stack,
            "OperationsAlarmTopic",
            topic_name="cloudops-incident-hub-operations",
            display_name="CloudOps Incident Hub operational alarms",
        )
        alarm_topic.add_subscription(
            subscriptions.EmailSubscription(alarm_notification_email)
        )
        action = cloudwatch_actions.SnsAction(alarm_topic)
        for construct_id in ALARM_IDS:
            alarm = cast(cloudwatch.Alarm, stack.node.find_child(construct_id))
            alarm.add_alarm_action(action)
            alarm.add_ok_action(action)

        CfnOutput(
            stack,
            "OperationsAlarmTopicArn",
            value=alarm_topic.topic_arn,
            description="SNS topic used for CloudWatch ALARM and OK notifications",
        )
