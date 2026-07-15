from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.validate_genai_shell_aws import (
    EXPECTED_ACTIONS,
    ValidationError,
    build_evidence,
    validate_evidence,
    validate_http_responses,
    validate_template,
    write_evidence_atomic,
)
from scripts.check_oidc_workflows import (
    validate_bootstrap_policy,
    validate_deploy_workflow,
)


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-ephemeral.yml"
BOOTSTRAP_TEMPLATE = ROOT / "bootstrap" / "github-oidc-role.yml"


def valid_template(prefix: str = "Random") -> dict:
    function = f"{prefix}Function"
    role = f"{prefix}Role"
    policy = f"{prefix}Policy"
    table = f"{prefix}Incidents"
    integration = f"{prefix}Integration"
    return {
        "Resources": {
            function: {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "FunctionName": "cloudops-genai-summary-function",
                    "Role": {"Fn::GetAtt": [role, "Arn"]},
                    "Environment": {
                        "Variables": {
                            "AI_SUMMARY_ENABLED": "false",
                            "AI_SUMMARY_PROVIDER": "disabled",
                            "TABLE_NAME": {"Ref": table},
                        }
                    },
                },
            },
            role: {
                "Type": "AWS::IAM::Role",
                "Properties": {"AssumeRolePolicyDocument": {"Statement": []}},
            },
            policy: {
                "Type": "AWS::IAM::Policy",
                "Properties": {
                    "Roles": [{"Ref": role}],
                    "PolicyDocument": {
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                "Resource": {"Fn::GetAtt": ["RandomLogs", "Arn"]},
                            },
                            {
                                "Effect": "Allow",
                                "Action": "dynamodb:GetItem",
                                "Resource": {"Fn::GetAtt": [table, "Arn"]},
                            },
                        ]
                    },
                },
            },
            table: {
                "Type": "AWS::DynamoDB::Table",
                "Properties": {"TableName": "cloudops-incidents"},
            },
            "RandomLogs": {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {
                    "LogGroupName": "/aws/lambda/cloudops-genai-summary-function"
                },
            },
            integration: {
                "Type": "AWS::ApiGatewayV2::Integration",
                "Properties": {
                    "IntegrationType": "AWS_PROXY",
                    "IntegrationUri": {"Fn::GetAtt": [function, "Arn"]},
                },
            },
            "RandomRoute": {
                "Type": "AWS::ApiGatewayV2::Route",
                "Properties": {
                    "RouteKey": "POST /incidents/{incident_id}/ai-summary",
                    "AuthorizationType": "JWT",
                    "AuthorizationScopes": [
                        "cloudops-incident-hub/incidents.summarize"
                    ],
                    "Target": {"Fn::Join": ["", ["integrations/", {"Ref": integration}]]},
                },
            },
            "ErrorsAlarm": {
                "Type": "AWS::CloudWatch::Alarm",
                "Properties": {"AlarmName": "cloudops-genai-summary-errors"},
            },
            "ThrottlesAlarm": {
                "Type": "AWS::CloudWatch::Alarm",
                "Properties": {"AlarmName": "cloudops-genai-summary-throttles"},
            },
            "Dashboard": {
                "Type": "AWS::CloudWatch::Dashboard",
                "Properties": {
                    "DashboardBody": (
                        "Invocations Errors Duration Throttles ConcurrentExecutions"
                    )
                },
            },
        }
    }


def genai_function(template: dict) -> dict:
    return next(
        resource
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::Lambda::Function"
    )


def genai_role(template: dict) -> dict:
    return next(
        resource
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::IAM::Role"
    )


def statements(template: dict) -> list[dict]:
    return next(
        resource["Properties"]["PolicyDocument"]["Statement"]
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
    )


def route(template: dict) -> dict:
    return next(
        resource["Properties"]
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::ApiGatewayV2::Route"
    )


def test_valid_template_follows_references_without_fixed_logical_ids():
    assert validate_template(valid_template("CompletelyDifferent")) == sorted(
        EXPECTED_ACTIONS
    )


def test_rejects_managed_policy_arns():
    template = valid_template()
    genai_role(template)["Properties"]["ManagedPolicyArns"] = ["managed-policy"]
    with pytest.raises(ValidationError, match="managed policies absent"):
        validate_template(template)


@pytest.mark.parametrize(
    "action",
    [
        "logs:CreateLogGroup",
        "dynamodb:BatchGetItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:BatchWriteItem",
        "cloudwatch:PutMetricData",
        "bedrock:Converse",
        "bedrock:InvokeModel",
        "s3:GetObject",
        "dynamodb:*",
    ],
)
def test_rejects_every_additional_or_wildcard_action(action: str):
    template = valid_template()
    statements(template)[0]["Action"].append(action)
    with pytest.raises(ValidationError, match="exact IAM actions"):
        validate_template(template)


@pytest.mark.parametrize("resource", ["table/index/by-time", "metrics-table"])
def test_rejects_get_item_outside_incident_table(resource: str):
    template = valid_template()
    statements(template)[1]["Resource"] = resource
    with pytest.raises(ValidationError, match="GetItem incident table resource"):
        validate_template(template)


@pytest.mark.parametrize(
    ("name", "value", "match"),
    [
        ("AI_SUMMARY_ENABLED", "true", "feature disabled"),
        ("AI_SUMMARY_PROVIDER", "bedrock", "provider disabled"),
        ("AI_SUMMARY_MODEL_ID", "configured-model", "forbidden Lambda"),
        ("AI_SUMMARY_ALLOWED_MODEL_IDS", "configured-model", "forbidden Lambda"),
        ("AWS_ACCESS_KEY_ID", "synthetic", "forbidden Lambda"),
        ("AWS_SECRET_ACCESS_KEY", "synthetic", "forbidden Lambda"),
        ("AWS_SESSION_TOKEN", "synthetic", "forbidden Lambda"),
    ],
)
def test_rejects_forbidden_configuration(name: str, value: str, match: str):
    template = valid_template()
    genai_function(template)["Properties"]["Environment"]["Variables"][name] = value
    with pytest.raises(ValidationError, match=match):
        validate_template(template)


@pytest.mark.parametrize(
    "token",
    ["inference profile", "arn:aws:bedrock", "BEDROCK_ENDPOINT", "InvokeModel"],
)
def test_rejects_bedrock_or_endpoint_configuration(token: str):
    template = valid_template()
    template["Metadata"] = {"Forbidden": token}
    with pytest.raises(ValidationError, match="Bedrock configuration absent"):
        validate_template(template)


def test_rejects_public_route():
    template = valid_template()
    route(template)["AuthorizationType"] = "NONE"
    with pytest.raises(ValidationError, match="JWT authorization"):
        validate_template(template)


def test_rejects_read_scope():
    template = valid_template()
    route(template)["AuthorizationScopes"] = [
        "cloudops-incident-hub/incidents.read"
    ]
    with pytest.raises(ValidationError, match="route scope"):
        validate_template(template)


def test_rejects_integration_with_another_lambda():
    template = valid_template()
    integration = next(
        item["Properties"]
        for item in template["Resources"].values()
        if item["Type"] == "AWS::ApiGatewayV2::Integration"
    )
    integration["IntegrationUri"] = {"Fn::GetAtt": ["AnotherFunction", "Arn"]}
    with pytest.raises(ValidationError, match="Lambda target"):
        validate_template(template)


def test_rejects_missing_route():
    template = valid_template()
    del template["Resources"]["RandomRoute"]
    with pytest.raises(ValidationError, match="single GenAI route"):
        validate_template(template)


def test_rejects_duplicate_route():
    template = valid_template()
    template["Resources"]["DuplicateRoute"] = copy.deepcopy(
        template["Resources"]["RandomRoute"]
    )
    with pytest.raises(ValidationError, match="single GenAI route"):
        validate_template(template)


def validate_good_http(anonymous: int = 401) -> None:
    validate_http_responses(
        authenticated_status=503,
        authenticated_headers="HTTP/2 503\ncontent-type: application/json\n",
        authenticated_body={"detail": "AI summary service is unavailable"},
        unauthenticated_status=anonymous,
        wrong_scope_status=403,
    )


@pytest.mark.parametrize("anonymous", [401, 403])
def test_accepts_closed_http_responses(anonymous: int):
    validate_good_http(anonymous)


@pytest.mark.parametrize("status", [200, 404, 500, 504])
def test_rejects_authenticated_status_other_than_503(status: int):
    with pytest.raises(ValidationError, match="authenticated HTTP status"):
        validate_http_responses(
            authenticated_status=status,
            authenticated_headers="content-type: application/json",
            authenticated_body={"detail": "AI summary service is unavailable"},
            unauthenticated_status=401,
            wrong_scope_status=403,
        )


@pytest.mark.parametrize(
    "body",
    [
        {"detail": "AI summary service is unavailable", "extra": True},
        {"detail": "AI summary service is unavailable", "summary": "synthetic"},
    ],
)
def test_rejects_authenticated_extra_fields(body: dict):
    with pytest.raises(ValidationError, match="authenticated closed response"):
        validate_http_responses(
            authenticated_status=503,
            authenticated_headers="content-type: application/json",
            authenticated_body=body,
            unauthenticated_status=401,
            wrong_scope_status=403,
        )


def test_rejects_anonymous_503():
    with pytest.raises(ValidationError, match="unauthenticated HTTP status"):
        validate_good_http(503)


@pytest.mark.parametrize("status", [401, 200, 404, 500, 503])
def test_rejects_wrong_scope_other_than_403(status: int):
    with pytest.raises(ValidationError, match="wrong-scope HTTP status"):
        validate_http_responses(
            authenticated_status=503,
            authenticated_headers="content-type: application/json",
            authenticated_body={"detail": "AI summary service is unavailable"},
            unauthenticated_status=401,
            wrong_scope_status=status,
        )


def evidence() -> dict:
    return build_evidence(
        commit_sha="a" * 40,
        workflow_run_id="12345",
        region="eu-west-1",
        timestamp="2030-01-01T00:00:00Z",
        unauthenticated_status=401,
    )


def test_evidence_has_only_allowed_fields_and_sorted_actions():
    result = evidence()
    validate_evidence(result)
    assert result["iam_actions"] == sorted(result["iam_actions"])
    rendered = json.dumps(result).lower()
    for forbidden in ('"incident_id":', "account_id", '"arn":', "token", "secret"):
        assert forbidden not in rendered


def test_evidence_rejects_extra_fields():
    result = evidence()
    result["incident_id"] = "synthetic"
    with pytest.raises(ValidationError, match="strict evidence fields"):
        validate_evidence(result)


@pytest.mark.parametrize("region", ["123456789012", "arn:synthetic:region"])
def test_evidence_rejects_sensitive_values(region: str):
    result = evidence()
    result["region"] = region
    with pytest.raises(ValidationError, match="sensitive evidence values"):
        validate_evidence(result)


def test_atomic_write_replaces_target_and_leaves_no_temporary_file(tmp_path: Path):
    target = tmp_path / "evidence.json"
    target.write_text("old", encoding="utf-8")
    write_evidence_atomic(target, evidence())
    assert json.loads(target.read_text(encoding="utf-8")) == evidence()
    assert list(tmp_path.iterdir()) == [target]


def test_equivalent_inputs_produce_equivalent_evidence():
    assert evidence() == evidence()


def test_errors_do_not_echo_templates_bodies_secrets_or_temporary_paths(tmp_path: Path):
    marker = "do-not-echo-sensitive-marker"
    template = valid_template()
    template["Sensitive"] = marker
    statements(template)[0]["Action"].append("bedrock:InvokeModel")
    with pytest.raises(ValidationError) as captured:
        validate_template(template)
    message = str(captured.value)
    assert marker not in message
    assert json.dumps(template) not in message
    assert str(tmp_path) not in message

    with pytest.raises(ValidationError) as captured_body:
        validate_http_responses(
            authenticated_status=503,
            authenticated_headers="content-type: application/json",
            authenticated_body={"detail": marker},
            unauthenticated_status=401,
            wrong_scope_status=403,
        )
    assert marker not in str(captured_body.value)


def workflow() -> str:
    return DEPLOY_WORKFLOW.read_text(encoding="utf-8")


def bootstrap() -> str:
    return BOOTSTRAP_TEMPLATE.read_text(encoding="utf-8")


def test_current_bootstrap_has_only_the_two_cleanup_read_actions():
    content = bootstrap()
    assert validate_bootstrap_policy(content) == []
    assert content.count("lambda:GetFunction") == 1
    assert content.count("logs:DescribeLogGroups") == 1
    assert "repo:${GitHubOwner}/${GitHubRepository}:environment:${GitHubEnvironment}" in content


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Action: lambda:GetFunction", "Action: s3:GetObject"),
        (
            "arn:${AWS::Partition}:lambda:${DeploymentRegion}:${AWS::AccountId}:function:cloudops-genai-summary-function",
            '"*"',
        ),
        ("function:cloudops-genai-summary-function", "function:another-function"),
        ("Action: lambda:GetFunction", "Action: lambda:*"),
        ("Action: lambda:GetFunction", "Action: lambda:InvokeFunction"),
        (
            "Action: lambda:GetFunction",
            "Action:\n                  - lambda:GetFunction\n                  - lambda:ListFunctions",
        ),
        ("Action: logs:DescribeLogGroups", "Action: s3:GetObject"),
        ("Action: logs:DescribeLogGroups", "Action: logs:*"),
        ("Action: logs:DescribeLogGroups", "Action: logs:GetLogEvents"),
        ("Action: logs:DescribeLogGroups", "Action: logs:FilterLogEvents"),
        (
            "Action: logs:DescribeLogGroups",
            "Action:\n                  - logs:DescribeLogGroups\n                  - logs:DescribeLogStreams",
        ),
        (
            "Action: logs:DescribeLogGroups\n                Resource: \"*\"",
            "Action: logs:DescribeLogGroups\n                Resource: !Sub restricted-resource",
        ),
        (
            "repo:${GitHubOwner}/${GitHubRepository}:environment:${GitHubEnvironment}",
            "repo:${GitHubOwner}/${GitHubRepository}:ref:refs/heads/main",
        ),
    ],
)
def test_bootstrap_guardrail_rejects_missing_or_broadened_cleanup_access(
    old: str, new: str
):
    mutated = bootstrap().replace(old, new, 1)
    assert mutated != bootstrap()
    assert validate_bootstrap_policy(mutated)


def test_current_deploy_workflow_passes_static_guardrails():
    assert validate_deploy_workflow(workflow()) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("          aws lambda get-function \\", "          aws lambda list-functions \\"),
        ("aws logs describe-log-groups", "aws logs describe-log-streams"),
        ("ResourceNotFoundException", "AccessDenied"),
        ("GenAI Lambda still exists", "Lambda result ignored"),
        ("GenAI Log Group still exists", "Log Group result ignored"),
        (
            "trap cleanup_verification_files EXIT",
            "echo cleanup files retained",
        ),
        (
            "> /tmp/genai-cleanup-function.json",
            "| tee evidence/get-function.json",
        ),
    ],
)
def test_workflow_guardrail_rejects_weakened_resource_cleanup(old: str, new: str):
    mutated = workflow().replace(old, new, 1)
    assert mutated != workflow()
    assert validate_deploy_workflow(mutated)


def test_cleanup_checks_follow_destroy_and_artifact_excludes_aws_responses():
    content = workflow()
    assert content.index("- name: Destroy ephemeral stack") < content.index(
        "- name: Verify stack removal"
    )
    artifact = content.split("- name: Upload sanitized GenAI shell evidence", 1)[1]
    artifact = artifact.split("- name:", 1)[0]
    assert "evidence/genai-shell-validation.json" in artifact
    for forbidden in ("get-function", "log-groups", "/tmp/", "responses"):
        assert forbidden not in artifact


def test_cleanup_never_reads_log_events_or_prints_get_function_response():
    content = workflow()
    cleanup = content.split("- name: Verify stack removal", 1)[1]
    cleanup = cleanup.split("- name:", 1)[0]
    for forbidden in (
        "filter-log-events",
        "get-log-events",
        "describe-log-streams",
        "logs tail",
        "tee",
    ):
        assert forbidden not in cleanup
    assert "> /tmp/genai-cleanup-function.json" in cleanup
    assert "2> /tmp/genai-cleanup-function-error.txt" in cleanup


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("VALIDATE-GENAI-SHELL-AND-DESTROY", "WRONG-CONFIRMATION"),
        ("environment: aws-ephemeral", "environment: missing"),
        ("aws-actions/configure-aws-credentials@v6.1.0", "actions/checkout@v4"),
        (
            "id: destroy\n        if: always() && steps.preflight.outcome == 'success' && steps.aws_credentials.outcome == 'success'",
            "id: destroy\n        if: success()",
        ),
        (
            "id: cleanup\n        if: always() && steps.preflight.outcome == 'success' && steps.aws_credentials.outcome == 'success' && steps.destroy.outcome == 'success'",
            "id: cleanup\n        if: success()",
        ),
        (
            "cloudops-incident-hub/incidents.read cloudops-incident-hub/incidents.write cloudops-incident-hub/incidents.summarize",
            "cloudops-incident-hub/incidents.read cloudops-incident-hub/incidents.write",
        ),
        (
            'PARTIAL_SCOPES="cloudops-incident-hub/incidents.read cloudops-incident-hub/incidents.write"',
            'PARTIAL_SCOPES="cloudops-incident-hub/incidents.read cloudops-incident-hub/incidents.write cloudops-incident-hub/incidents.summarize"',
        ),
        ("::add-mask::$CLIENT_SECRET", "client secret available"),
        ("::add-mask::$FULL_TOKEN", "full token available"),
        ("::add-mask::$PARTIAL_TOKEN", "partial token available"),
        (
            "path: evidence/genai-shell-validation.json",
            "path: |\n            evidence/genai-shell-validation.json\n            /tmp/template.json",
        ),
        ("aws sts get-caller-identity > /tmp/aws-identity.json", "aws sts get-caller-identity"),
        ("-c enable_load_test_client=true", "-c enable_load_test_client=false"),
    ],
)
def test_workflow_guardrail_rejects_missing_or_weakened_controls(old: str, new: str):
    mutated = workflow().replace(old, new, 1)
    assert mutated != workflow()
    assert validate_deploy_workflow(mutated)


@pytest.mark.parametrize(
    "addition",
    [
        "\n  push:\n    branches: [main]\n",
        "\n          set -x\n",
        "\n          aws bedrock-runtime converse\n",
    ],
)
def test_workflow_guardrail_rejects_automatic_tracing_or_bedrock(addition: str):
    mutated = workflow().replace("permissions:\n", addition + "permissions:\n", 1)
    assert validate_deploy_workflow(mutated)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('test "$RUN_SMOKE_TEST" = "false"', 'test "$RUN_SMOKE_TEST" = "true"'),
        ('test "$RUN_CHATOPS_TEST" = "false"', 'test "$RUN_CHATOPS_TEST" = "true"'),
        ('test "$CONFIRMATION" = "DEPLOY-AND-DESTROY"', 'test "$CONFIRMATION" = "VALIDATE-GENAI-SHELL-AND-DESTROY"'),
        ('test "$CONFIRMATION" = "VALIDATE-GENAI-SHELL-AND-DESTROY"', 'test "$CONFIRMATION" = "DEPLOY-AND-DESTROY"'),
        ('if [ "$RUN_SMOKE_TEST" != "true" ]', 'if [ "$RUN_SMOKE_TEST" = "false" ]'),
        ("    steps:\n", "    steps:\n      - uses: aws-actions/configure-aws-credentials@v6.1.0\n"),
        ("steps.preflight.outputs.profile == 'legacy' && steps.aws_credentials.outcome", "steps.aws_credentials.outcome"),
        ("always() && steps.preflight.outcome == 'success' && steps.preflight.outputs.profile == 'legacy' && steps.aws_credentials.outcome", "failure() && steps.aws_credentials.outcome"),
        ("steps.preflight.outputs.profile == 'legacy' && inputs.run_smoke_test", "inputs.run_smoke_test"),
        ("steps.preflight.outputs.profile == 'legacy' && (inputs.run_smoke_test", "steps.preflight.outputs.profile == 'genai-shell' && (inputs.run_smoke_test"),
        ("steps.preflight.outcome == 'success' && steps.preflight.outputs.profile == 'legacy' && (inputs.run_smoke_test", "steps.preflight.outputs.profile == 'legacy' && (inputs.run_smoke_test"),
        ("id: destroy", "id: destroy-late",),
        ("id: cleanup", "id: cleanup-late",),
        ("id: evidence", "id: evidence-late",),
        ("path: evidence/genai-shell-validation.json", "path: evidence/"),
        ("steps.preflight.outputs.profile == 'legacy' && (inputs.run_smoke_test", "steps.preflight.outputs.profile == 'genai-shell' && (inputs.run_smoke_test"),
        ("--config /tmp/genai-oauth-curl.conf", '--user "$LOADTESTCLIENTID:$CLIENT_SECRET"'),
        ("--config /tmp/genai-oauth-curl.conf", '-u "$LOADTESTCLIENTID:$CLIENT_SECRET"'),
        ("--config /tmp/genai-oauth-curl.conf", '--header "Authorization: Basic synthetic"'),
        ("          umask 077", "          umask 022"),
        ("          chmod 600 /tmp/genai-oauth-curl.conf", "          chmod 644 /tmp/genai-oauth-curl.conf"),
        ("/tmp/genai-oauth-curl.conf /tmp/genai-*", "/tmp/genai-*"),
        ("outputs_file=\"/tmp/genai-cdk-outputs.json\"", "outputs_file=\"../evidence/cdk-outputs.json\""),
        ("      - name: Remove GenAI validation temporary files", "      - name: Removed cleanup step"),
        ("rm -f /tmp/genai-oauth-curl.conf /tmp/client-secret.txt", "rm -f /tmp/genai-oauth-curl.conf"),
        ('test "$outcome" = "success"', 'test "$outcome" != "failure"'),
        ("            legacy)", "            legacy-disabled)"),
    ],
)
def test_profile_isolation_guardrail_rejects_regressions(old: str, new: str):
    mutated = workflow().replace(old, new, 1)
    assert mutated != workflow()
    assert validate_deploy_workflow(mutated)


def test_profiles_are_mutually_exclusive_and_keep_legacy_routes():
    content = workflow()
    assert "default: genai-shell" in content
    assert "VALIDATE-GENAI-SHELL-AND-DESTROY" in content
    assert "DEPLOY-AND-DESTROY" in content
    diagnostics = content.split("- name: Collect asynchronous processor diagnostics", 1)[1]
    diagnostics = diagnostics.split("- name:", 1)[0]
    assert "steps.preflight.outcome == 'success'" in diagnostics
    assert "steps.preflight.outputs.profile == 'legacy'" in diagnostics
    assert "filter-log-events" in diagnostics


def test_genai_artifact_is_sanitized_and_ordered_after_cleanup():
    content = workflow()
    assert content.index("id: destroy") < content.index("id: cleanup")
    assert content.index("id: cleanup") < content.index("id: evidence")
    assert content.index("id: evidence") < content.index("id: genai_upload")
    assert content.index("id: genai_upload") < content.index("id: temp_cleanup")
    upload = content.split("- name: Upload sanitized GenAI shell evidence", 1)[1]
    upload = upload.split("- name:", 1)[0]
    assert "path: evidence/genai-shell-validation.json" in upload
    assert "path: evidence/\n" not in upload


def test_oauth_secret_is_not_in_argv_and_has_dual_cleanup():
    content = workflow()
    assert "curl --user" not in content
    assert "curl -u" not in content
    assert "Authorization: Basic" not in content
    assert content.count("--config /tmp/genai-oauth-curl.conf") == 2
    assert "umask 077" in content
    assert "chmod 600 /tmp/genai-oauth-curl.conf" in content
    assert "trap cleanup_temporaries EXIT" in content
    assert "rm -f /tmp/genai-oauth-curl.conf /tmp/client-secret.txt" in content
