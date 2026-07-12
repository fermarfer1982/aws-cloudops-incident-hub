from aws_cdk import App
from aws_cdk.assertions import Match, Template

from cloudops_infra.reliability import apply_reliability_controls
from cloudops_infra.stack import CloudOpsIncidentHubStack


def get_template(
    *,
    persistent_environment: bool = False,
    alarm_notification_email: str | None = None,
    slack_workspace_id: str | None = None,
    slack_channel_id: str | None = None,
) -> Template:
    app = App()
    stack = CloudOpsIncidentHubStack(app, "TestStack", bundle_dependencies=False)
    apply_reliability_controls(
        stack,
        persistent_environment=persistent_environment,
        alarm_notification_email=alarm_notification_email,
        slack_workspace_id=slack_workspace_id,
        slack_channel_id=slack_channel_id,
    )
    return Template.from_stack(stack)


def test_ephemeral_mode_preserves_destroy_semantics_and_has_no_alarm_topic():
    template = get_template()
    resources = template.to_json()["Resources"]
    tables = [
        resource
        for resource in resources.values()
        if resource["Type"] == "AWS::DynamoDB::Table"
    ]

    assert len(tables) == 2
    assert all(table["DeletionPolicy"] == "Delete" for table in tables)
    assert all(table["UpdateReplacePolicy"] == "Delete" for table in tables)
    assert all(
        "PointInTimeRecoverySpecification" not in table["Properties"]
        for table in tables
    )
    template.resource_count_is("AWS::SNS::Topic", 0)
    template.resource_count_is("AWS::SNS::Subscription", 0)
    template.has_output("DataProtectionMode", {"Value": "ephemeral-destroy"})


def test_persistent_mode_enables_pitr_retains_tables_and_keeps_logs_for_30_days():
    template = get_template(persistent_environment=True)
    resources = template.to_json()["Resources"]
    tables = [
        resource
        for resource in resources.values()
        if resource["Type"] == "AWS::DynamoDB::Table"
    ]
    log_groups = [
        resource
        for resource in resources.values()
        if resource["Type"] == "AWS::Logs::LogGroup"
    ]

    assert len(tables) == 2
    assert all(table["DeletionPolicy"] == "Retain" for table in tables)
    assert all(table["UpdateReplacePolicy"] == "Retain" for table in tables)
    assert all(
        table["Properties"]["PointInTimeRecoverySpecification"]
        == {"PointInTimeRecoveryEnabled": True}
        for table in tables
    )

    assert len(log_groups) == 2
    assert all(log_group["DeletionPolicy"] == "Retain" for log_group in log_groups)
    assert all(log_group["UpdateReplacePolicy"] == "Retain" for log_group in log_groups)
    assert all(log_group["Properties"]["RetentionInDays"] == 30 for log_group in log_groups)
    template.has_output("DataProtectionMode", {"Value": "persistent-pitr-retain"})


def test_alarm_email_creates_sns_subscription_and_routes_alarm_and_ok_states():
    template = get_template(alarm_notification_email="ops@example.com")
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.has_resource_properties(
        "AWS::SNS::Subscription",
        {
            "Protocol": "email",
            "Endpoint": "ops@example.com",
            "TopicArn": Match.any_value(),
        },
    )

    resources = template.to_json()["Resources"]
    alarms = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    ]
    assert len(alarms) == 4
    assert all(len(alarm.get("AlarmActions", [])) == 1 for alarm in alarms)
    assert all(len(alarm.get("OKActions", [])) == 1 for alarm in alarms)
    template.has_output("OperationsAlarmTopicArn", {"Value": Match.any_value()})


def test_invalid_alarm_email_is_rejected():
    app = App()
    stack = CloudOpsIncidentHubStack(app, "TestStack", bundle_dependencies=False)

    try:
        apply_reliability_controls(stack, alarm_notification_email="invalid")
    except ValueError as exc:
        assert "alarm_notification_email" in str(exc)
    else:
        raise AssertionError("Invalid alarm email was accepted")



def test_slack_creates_notification_only_chatops_configuration():
    template = get_template(
        slack_workspace_id="T0123456789",
        slack_channel_id="C0123456789",
    )

    template.resource_count_is("AWS::SNS::Topic", 1)
    template.resource_count_is(
        "AWS::Chatbot::SlackChannelConfiguration",
        1,
    )
    template.resource_count_is("AWS::IAM::ManagedPolicy", 1)

    template.has_resource_properties(
        "AWS::Chatbot::SlackChannelConfiguration",
        {
            "ConfigurationName": (
                "cloudops-incident-hub-operations"
            ),
            "SlackWorkspaceId": "T0123456789",
            "SlackChannelId": "C0123456789",
            "LoggingLevel": "NONE",
            "UserRoleRequired": False,
            "SnsTopicArns": Match.any_value(),
            "GuardrailPolicies": Match.any_value(),
        },
    )

    resources = template.to_json()["Resources"]

    slack_configurations = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"]
        == "AWS::Chatbot::SlackChannelConfiguration"
    ]

    assert len(slack_configurations) == 1

    slack_properties = slack_configurations[0]

    assert len(slack_properties["SnsTopicArns"]) == 1
    assert len(slack_properties["GuardrailPolicies"]) == 1

    managed_policies = [
        resource
        for resource in resources.values()
        if resource["Type"] == "AWS::IAM::ManagedPolicy"
    ]

    assert len(managed_policies) == 1

    policy = str(
        managed_policies[0]["Properties"]["PolicyDocument"]
    )

    for permission in (
        "cloudwatch:Describe*",
        "cloudwatch:Get*",
        "cloudwatch:List*",
        "sns:GetTopicAttributes",
        "sns:List*",
    ):
        assert permission in policy

    assert "AdministratorAccess" not in str(resources)

    alarms = [
        resource["Properties"]
        for resource in resources.values()
        if resource["Type"] == "AWS::CloudWatch::Alarm"
    ]

    assert len(alarms) == 4
    assert all(
        len(alarm.get("AlarmActions", [])) == 1
        for alarm in alarms
    )
    assert all(
        len(alarm.get("OKActions", [])) == 1
        for alarm in alarms
    )


def test_slack_identifiers_must_be_provided_together():
    cases = (
        ("T0123456789", None),
        (None, "C0123456789"),
    )

    for workspace_id, channel_id in cases:
        app = App()
        stack = CloudOpsIncidentHubStack(
            app,
            "TestStack",
            bundle_dependencies=False,
        )

        try:
            apply_reliability_controls(
                stack,
                slack_workspace_id=workspace_id,
                slack_channel_id=channel_id,
            )
        except ValueError as exc:
            assert "must be provided together" in str(exc)
        else:
            raise AssertionError(
                "Incomplete Slack identifiers were accepted"
            )


def test_invalid_slack_identifier_prefixes_are_rejected():
    cases = (
        (
            "invalid-workspace",
            "C0123456789",
            "slack_workspace_id",
        ),
        (
            "T0123456789",
            "invalid-channel",
            "slack_channel_id",
        ),
    )

    for workspace_id, channel_id, expected_error in cases:
        app = App()
        stack = CloudOpsIncidentHubStack(
            app,
            "TestStack",
            bundle_dependencies=False,
        )

        try:
            apply_reliability_controls(
                stack,
                slack_workspace_id=workspace_id,
                slack_channel_id=channel_id,
            )
        except ValueError as exc:
            assert expected_error in str(exc)
        else:
            raise AssertionError(
                "Invalid Slack identifier was accepted"
            )
