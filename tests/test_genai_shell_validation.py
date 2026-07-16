from __future__ import annotations

import base64
import copy
import json
import os
import re
import stat
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
    AWS_PERFORMANCE,
    DESTROY,
    OIDC_ACTION_REPOSITORY,
    OIDC_PREFLIGHT,
    WorkflowUse,
    _workflow_uses,
    OAuthConfigError,
    escape_github_command_value,
    main as oidc_main,
    validate_bootstrap_policy,
    validate_deploy_workflow,
    validate_oidc_credential_actions,
    validate_sensitive_logging_source,
    write_oauth_curl_config,
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


OIDC_ACTION_PATTERN = re.compile(
    rf"(?m)^(?P<indent>\s*uses:\s*){re.escape(OIDC_ACTION_REPOSITORY)}@[^\s#]+\s*$"
)


def replace_oidc_action(content: str, reference: str) -> str:
    matches = list(OIDC_ACTION_PATTERN.finditer(content))
    assert len(matches) == 1, "fixture must contain exactly one credential action"
    return OIDC_ACTION_PATTERN.sub(
        rf"\g<indent>{OIDC_ACTION_REPOSITORY}@{reference}", content, count=1
    )


def oidc_workflows() -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in (OIDC_PREFLIGHT, AWS_PERFORMANCE, DEPLOY_WORKFLOW, DESTROY)
    }


def insert_workflow_step(
    content: str, *, uses: str, before_official: bool, name: str = "Helper"
) -> str:
    action_match = OIDC_ACTION_PATTERN.search(content)
    assert action_match is not None
    action_position = action_match.start()
    starts = [match.start() for match in re.finditer(r"(?m)^      - (?:name|uses):", content)]
    current = max(position for position in starts if position < action_position)
    later = [position for position in starts if position > action_position]
    insertion = current if before_official else min(later)
    step = f"      - name: {name}\n        uses: {uses}\n\n"
    return content[:insertion] + step + content[insertion:]


def insert_raw_workflow_step(
    content: str, raw_step: str, *, before_official: bool = False
) -> str:
    action_match = OIDC_ACTION_PATTERN.search(content)
    assert action_match is not None
    action_position = action_match.start()
    starts = [match.start() for match in re.finditer(r"(?m)^      - (?:name|uses):", content)]
    current = max(position for position in starts if position < action_position)
    later = [position for position in starts if position > action_position]
    insertion = current if before_official else min(later)
    return content[:insertion] + raw_step + "\n" + content[insertion:]


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


@pytest.mark.parametrize("reference", ["v6.2.2", "v6.2.3", "v6.3.0", "v6.10.1"])
def test_oidc_action_accepts_supported_prefixed_versions(reference: str):
    contents = {
        path: replace_oidc_action(content, reference)
        for path, content in oidc_workflows().items()
    }
    assert validate_oidc_credential_actions(contents) == []


@pytest.mark.parametrize("reference", ["6.2.2", "6.2.3", "6.3.0", "6.10.1"])
def test_oidc_action_accepts_official_unprefixed_versions(reference: str):
    contents = {
        path: replace_oidc_action(content, reference)
        for path, content in oidc_workflows().items()
    }
    assert validate_oidc_credential_actions(contents) == []


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        ("v6.1.0", "version must be at least 6.2.2"),
        ("v6.2.1", "version must be at least 6.2.2"),
        ("v5.9.9", "major must be 6"),
        ("v7.0.0", "major must be 6"),
        ("v6", "must use a canonical full semantic version"),
        ("v6.2", "must use a canonical full semantic version"),
        ("v6.2.2-beta", "must use a canonical full semantic version"),
        ("main", "must use a canonical full semantic version"),
        ("latest", "must use a canonical full semantic version"),
        ("a" * 40, "must use a canonical full semantic version"),
        ("release-v6.2.2", "must use a canonical full semantic version"),
    ],
)
def test_oidc_action_rejects_unsupported_references(reference: str, message: str):
    errors = validate_oidc_credential_actions(
        {"workflow": replace_oidc_action(workflow(), reference)}
    )
    assert any(message in error for error in errors)


@pytest.mark.parametrize(
    "repository",
    ["example/configure-aws-credentials", "aws-actions/configure_aws_credentials"],
)
def test_oidc_action_rejects_alternative_repository(repository: str):
    mutated = workflow().replace(OIDC_ACTION_REPOSITORY, repository, 1)
    errors = validate_oidc_credential_actions({"workflow": mutated})
    assert any("must use the official repository" in error for error in errors)


@pytest.mark.parametrize(
    "uses",
    [
        "attacker/configure-aws-credentials@v6.2.2",
        "./configure-aws-credentials",
        "./actions/configure-aws-credentials",
        "attacker/configure_aws_credentials@v6.2.2",
        "attacker/configure.aws.credentials@v6.2.2",
        "AWS-ACTIONS/configure-aws-credentials@v6.2.2",
        "attacker/configure-aws-credentials@v6.2.2 # inline comment",
    ],
)
@pytest.mark.parametrize("before_official", [False, True])
def test_oidc_action_rejects_alternative_candidate_in_any_step(
    uses: str, before_official: bool
):
    mutated = insert_workflow_step(
        workflow(),
        uses=uses,
        before_official=before_official,
        name="Secondary credential action" if before_official else "Helper",
    )
    errors = validate_oidc_credential_actions({"workflow": mutated})
    assert errors == [
        "workflow: OIDC credential action must use the official repository"
    ]


@pytest.mark.parametrize("path", [OIDC_PREFLIGHT, AWS_PERFORMANCE, DEPLOY_WORKFLOW, DESTROY])
def test_oidc_action_rejects_alternative_candidate_in_every_workflow(path: Path):
    content = path.read_text(encoding="utf-8")
    mutated = insert_workflow_step(
        content,
        uses="attacker/configure-aws-credentials@v6.2.2",
        before_official=False,
    )
    errors = validate_oidc_credential_actions({path: mutated})
    assert any("must use the official repository" in error for error in errors)


@pytest.mark.parametrize("path", [OIDC_PREFLIGHT, AWS_PERFORMANCE, DEPLOY_WORKFLOW, DESTROY])
@pytest.mark.parametrize(
    "uses",
    [
        "attacker/configure-aws-credentials/subaction@v6.2.2",
        "aws-actions/configure-aws-credentials/subaction@v6.2.2",
        "attacker/other/configure-aws-credentials@v6.2.2",
        "attacker/other/configure_aws_credentials/helper@v6.2.2",
        "attacker/configure.aws.credentials/subaction@v6.2.2",
        "attacker/configure--aws--credentials/helper@v6.2.2",
        "./configure-aws-credentials/subaction",
        "./actions/configure-aws-credentials/subaction",
        "../configure-aws-credentials/helper",
    ],
)
def test_oidc_action_rejects_candidate_in_any_remote_or_local_component(
    path: Path, uses: str
):
    content = path.read_text(encoding="utf-8")
    mutated = insert_workflow_step(
        content,
        uses=uses,
        before_official=False,
    )
    errors = validate_oidc_credential_actions({path: mutated})
    assert any("must use the official repository" in error for error in errors)


@pytest.mark.parametrize("path", [OIDC_PREFLIGHT, AWS_PERFORMANCE, DEPLOY_WORKFLOW, DESTROY])
@pytest.mark.parametrize(
    "uses",
    [
        "attacker/configure-aws-credentials/.github/workflows/helper.yml@v1",
        "aws-actions/configure-aws-credentials/.github/workflows/helper.yml@v6.2.2",
    ],
)
def test_oidc_action_rejects_candidate_reusable_workflow(path: Path, uses: str):
    content = path.read_text(encoding="utf-8")
    mutated = content + f"\n  credential_helper:\n    uses: {uses}\n"
    errors = validate_oidc_credential_actions({path: mutated})
    assert any("must be declared as a step action" in error for error in errors)


@pytest.mark.parametrize("path", [OIDC_PREFLIGHT, AWS_PERFORMANCE, DEPLOY_WORKFLOW, DESTROY])
def test_oidc_action_rejects_scalar_anchor_and_alias_in_every_workflow(path: Path):
    content = path.read_text(encoding="utf-8")
    anchored = (
        "env:\n"
        "  CREDENTIAL_ACTION: &credential_action "
        "attacker/configure-aws-credentials@v6.2.2\n\n"
        + content
    )
    mutated = insert_workflow_step(
        anchored,
        uses="*credential_action",
        before_official=False,
    )
    errors = validate_oidc_credential_actions({path: mutated})
    assert any("YAML anchors and aliases are forbidden" in error for error in errors)


@pytest.mark.parametrize(
    ("prefix", "raw_step", "message"),
    [
        (
            "x-credential-step: &credential_step\n"
            "  uses: attacker/configure-aws-credentials@v6.2.2\n\n",
            "      - <<: *credential_step\n        name: Helper\n",
            "YAML anchors and aliases are forbidden",
        ),
        (
            "x-credential-step: &credential_step\n"
            "  name: Helper\n"
            "  uses: attacker/configure-aws-credentials@v6.2.2\n\n",
            "      - *credential_step\n",
            "YAML anchors and aliases are forbidden",
        ),
        (
            "",
            "      - &credential_step\n"
            "        name: Helper\n"
            "        uses: attacker/configure-aws-credentials@v6.2.2\n",
            "YAML anchors and aliases are forbidden",
        ),
        (
            "x-credential-step: &credential_step\n"
            "  uses: attacker/configure-aws-credentials@v6.2.2\n\n",
            "      - <<: *credential_step\n        name: Helper\n",
            "YAML merge keys are forbidden",
        ),
    ],
)
def test_oidc_action_rejects_anchored_mappings_and_merge_keys(
    prefix: str, raw_step: str, message: str
):
    mutated = prefix + insert_raw_workflow_step(workflow(), raw_step)
    errors = validate_oidc_credential_actions({"workflow": mutated})
    assert any(message in error for error in errors)


@pytest.mark.parametrize(
    ("raw_step", "message"),
    [
        (
            "      - { name: Helper, uses: attacker/configure-aws-credentials@v6.2.2 }\n",
            "steps must use canonical block mappings",
        ),
        (
            "      - name: Helper\n"
            '        "uses": attacker/configure-aws-credentials@v6.2.2\n',
            "steps must use canonical block mappings",
        ),
        (
            "      - name: Helper\n"
            "        ? uses\n"
            "        : attacker/configure-aws-credentials@v6.2.2\n",
            "steps must use canonical block mappings",
        ),
        (
            "      - name: Helper\n"
            "        uses: >\n"
            "          attacker/configure-aws-credentials@v6.2.2\n",
            "uses values must be explicit scalar strings",
        ),
        (
            "      - name: Helper\n"
            "        uses: |\n"
            "          attacker/configure-aws-credentials@v6.2.2\n",
            "uses values must be explicit scalar strings",
        ),
        (
            "      - name: Helper\n"
            "        uses: [attacker/configure-aws-credentials@v6.2.2]\n",
            "uses values must be explicit scalar strings",
        ),
        (
            "      - name: Helper\n"
            "        uses: aws-actions/configure-aws-credentials@v6.2.2\n"
            "        uses: attacker/unrelated-action@v1\n",
            "must not contain duplicate uses keys",
        ),
        (
            "      - name: Helper\n"
            "        uses: attacker/unrelated-action@v1\n"
            "        uses: aws-actions/configure-aws-credentials@v6.2.2\n",
            "must not contain duplicate uses keys",
        ),
    ],
)
def test_oidc_action_rejects_ambiguous_step_yaml(raw_step: str, message: str):
    mutated = insert_raw_workflow_step(workflow(), raw_step)
    errors = validate_oidc_credential_actions({"workflow": mutated})
    assert any(message in error for error in errors)


def test_oidc_action_rejects_job_flow_mapping_with_candidate_uses():
    mutated = workflow() + (
        "\n  helper: { uses: "
        "attacker/configure-aws-credentials/.github/workflows/helper.yml@v1 }\n"
    )
    errors = validate_oidc_credential_actions({"workflow": mutated})
    assert any("steps must use canonical block mappings" in error for error in errors)


def test_oidc_action_rejects_alias_even_when_it_resolves_to_official_action():
    anchored = (
        "env:\n"
        "  CREDENTIAL_ACTION: &credential_action "
        "aws-actions/configure-aws-credentials@v6.2.2\n\n"
        + workflow()
    )
    mutated = insert_workflow_step(
        anchored, uses="*credential_action", before_official=False
    )
    errors = validate_oidc_credential_actions({"workflow": mutated})
    assert any("YAML anchors and aliases are forbidden" in error for error in errors)


def test_workflow_uses_extractor_reports_locations_and_stable_order():
    extracted, errors = _workflow_uses(workflow())
    assert errors == []
    assert extracted
    assert all(isinstance(item, WorkflowUse) for item in extracted)
    assert all(item.location == "step" for item in extracted)
    assert [item.line for item in extracted] == sorted(item.line for item in extracted)
    assert sum(item.value == f"{OIDC_ACTION_REPOSITORY}@v6.2.2" for item in extracted) == 1


def test_workflow_uses_extractor_excludes_comments_and_block_scalars():
    marker = "ARBITRARY-SENSITIVE-MARKER"
    harmless = (
        'env:\n  DESCRIPTION: "&credential_action *credential_action <<:"\n\n'
        + workflow()
    ).replace(
        "permissions:\n",
        "# &credential_action *credential_action <<: " + marker + "\npermissions:\n",
        1,
    )
    harmless = harmless.replace(
        "      - name: Verify AWS identity\n",
        "      - name: Harmless YAML-looking shell\n"
        "        run: |\n"
        "          echo '&credential_action *credential_action <<:'\n"
        "          uses: attacker/configure-aws-credentials@v6.2.2\n\n"
        "      - name: Verify AWS identity\n",
        1,
    )
    extracted, errors = _workflow_uses(harmless)
    assert errors == []
    assert not any("attacker/configure-aws-credentials" in item.value for item in extracted)
    assert marker not in " ".join(errors)


def test_workflow_uses_extractor_reports_duplicate_without_arbitrary_content():
    marker = "ARBITRARY-SENSITIVE-MARKER"
    raw_step = (
        "      - name: " + marker + "\n"
        "        uses: actions/checkout@v4\n"
        "        uses: actions/setup-python@v5\n"
    )
    _, errors = _workflow_uses(insert_raw_workflow_step(workflow(), raw_step))
    assert errors == ["OIDC workflow steps must not contain duplicate uses keys"]
    assert marker not in " ".join(errors)


def test_oidc_action_ignores_comments_run_strings_and_unrelated_actions():
    current = workflow()
    harmless = current.replace(
        "permissions:\n",
        "# uses: attacker/configure-aws-credentials@v6.2.2\npermissions:\n",
        1,
    )
    harmless = harmless.replace(
        "      - name: Verify AWS identity\n",
        "      - name: Explain credential action\n"
        "        run: |\n"
        "          uses: attacker/configure-aws-credentials@v6.2.2\n\n"
        "      - name: Unrelated action\n"
        "        uses: actions/setup-python@v5\n\n"
        "      - name: Verify AWS identity\n",
        1,
    )
    assert validate_oidc_credential_actions({"workflow": harmless}) == []


@pytest.mark.parametrize(
    "reference",
    [
        "v06.2.2",
        "v6.02.2",
        "v6.2.02",
        "06.2.2",
        "6.02.2",
        "6.2.02",
        "v0006.0002.0002",
        "0006.0002.0002",
        "v6.002.0002",
        "v6.2.2.0",
    ],
)
def test_oidc_action_rejects_noncanonical_semver_in_all_workflows(reference: str):
    contents = {
        path: replace_oidc_action(content, reference)
        for path, content in oidc_workflows().items()
    }
    errors = validate_oidc_credential_actions(contents)
    assert len(errors) == 4
    assert all("must use a canonical full semantic version" in error for error in errors)


def test_oidc_action_fixture_replacement_requires_exactly_one_action():
    current = workflow()
    missing = OIDC_ACTION_PATTERN.sub("", current, count=1)
    duplicate = current.replace(
        OIDC_ACTION_PATTERN.search(current).group(0),
        f"{OIDC_ACTION_PATTERN.search(current).group(0)}\n"
        f"{OIDC_ACTION_PATTERN.search(current).group(0)}",
        1,
    )
    with pytest.raises(AssertionError, match="exactly one credential action"):
        replace_oidc_action(missing, "v6.2.3")
    with pytest.raises(AssertionError, match="exactly one credential action"):
        replace_oidc_action(duplicate, "v6.2.3")


def test_oidc_action_rejects_missing_or_duplicate_action():
    current = workflow()
    action_line = OIDC_ACTION_PATTERN.search(current)
    assert action_line is not None
    missing = OIDC_ACTION_PATTERN.sub("", current, count=1)
    duplicate = current.replace(action_line.group(0), f"{action_line.group(0)}\n{action_line.group(0)}", 1)
    assert any(
        "OIDC credential action is required" in error
        for error in validate_oidc_credential_actions({"workflow": missing})
    )
    assert any(
        "must appear exactly once per workflow" in error
        for error in validate_oidc_credential_actions({"workflow": duplicate})
    )


def test_oidc_action_rejects_inconsistent_versions_and_styles():
    contents = oidc_workflows()
    paths = list(contents)
    inconsistent = {
        path: replace_oidc_action(content, "v6.2.3" if path == paths[0] else "v6.2.2")
        for path, content in contents.items()
    }
    mixed_style = {
        path: replace_oidc_action(content, "6.2.2" if path == paths[0] else "v6.2.2")
        for path, content in contents.items()
    }
    for candidate in (inconsistent, mixed_style):
        assert any(
            "version must be consistent across workflows" in error
            for error in validate_oidc_credential_actions(candidate)
        )


@pytest.mark.parametrize(
    ("old", "message"),
    [
        ("          role-to-assume:", "OIDC credential action requires role-to-assume"),
        ("          aws-region:", "OIDC credential action requires aws-region"),
        ("          allowed-account-ids:", "OIDC credential action requires allowed-account-ids"),
        ("  id-token: write", "permissions.id-token must be write"),
    ],
)
def test_oidc_controls_remain_required(old: str, message: str):
    mutated = workflow().replace(old, old.replace(":", "-removed:", 1), 1)
    errors = validate_deploy_workflow(mutated)
    assert any(message in error for error in errors)


@pytest.mark.parametrize(
    "addition", ["          aws-access-key-id: synthetic\n", "          aws-secret-access-key: synthetic\n"]
)
def test_oidc_controls_reject_static_credentials(addition: str):
    mutated = workflow().replace("          role-to-assume:", addition + "          role-to-assume:", 1)
    errors = validate_deploy_workflow(mutated)
    assert any("static AWS" in error for error in errors)


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
        ("outputs_file=\"/tmp/genai-cdk-outputs.json\"", "outputs_file=\"../evidence/cdk-outputs.json\""),
        ("      - name: Remove GenAI validation temporary files", "      - name: Removed cleanup step"),
        ("rm -f /tmp/genai-oauth-curl.conf /tmp/genai-client-secret.json", "rm -f /tmp/genai-oauth-curl.conf"),
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
    assert "write-oauth-curl-config" in content
    assert "trap cleanup_temporaries EXIT" in content
    assert "rm -f /tmp/genai-oauth-curl.conf /tmp/genai-client-secret.json" in content
    assert "CLIENT_SECRET" not in content


@pytest.mark.parametrize(
    ("client_id", "secret"),
    [
        ('client"id', 'secret"value'),
        ("client'id", "secret'value"),
        (r"client\id", r"secret\value"),
        ("client\rid", "secret\rvalue"),
        ("client\nid", "secret\nvalue"),
        ("client\r\nid", "secret\r\nvalue"),
        ("client%id", "secret%value"),
        ("client id", "secret value"),
        ("client=id", "secret=value"),
        ("client:id", "secret:value"),
        ("cliente-ñ", "secreto-雪"),
        ("client", 'header = "X-Injected: yes"'),
        ("client", 'url = "https://example.invalid"'),
        ("client", 'proxy = "attacker.invalid"'),
    ],
)
def test_oauth_config_encodes_adversarial_values_as_data(
    tmp_path: Path, client_id: str, secret: str
):
    secret_json = tmp_path / "secret.json"
    output = tmp_path / "curl.conf"
    mask_output = tmp_path / "mask-values.txt"
    secret_json.write_text(json.dumps(secret), encoding="utf-8")

    assert write_oauth_curl_config(
        secret_json=secret_json,
        output=output,
        mask_output=mask_output,
        client_id=client_id,
    ) is None

    basic = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    rendered = output.read_text(encoding="ascii")
    assert rendered == f'header = "Authorization: Basic {basic}"\n'
    assert len(rendered.splitlines()) == 1
    assert client_id not in rendered
    assert secret not in rendered
    assert base64.b64decode(basic) == f"{client_id}:{secret}".encode("utf-8")
    assert not any(
        directive in rendered
        for directive in ('X-Injected: yes', 'url = "', 'proxy = "')
    )
    assert stat.S_IMODE(mask_output.stat().st_mode) == 0o600
    assert mask_output.read_text(encoding="utf-8").splitlines() == [
        escape_github_command_value(secret),
        escape_github_command_value(basic),
    ]
    assert mask_output.read_bytes().endswith(b"\n")


def test_oauth_cli_masks_secret_and_basic_with_workflow_escaping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    client_id = "client%\r\n雪"
    secret = "secret%\r\n雪"
    secret_json = tmp_path / "secret.json"
    output = tmp_path / "curl.conf"
    mask_output = tmp_path / "mask-values.txt"
    secret_json.write_text(json.dumps(secret), encoding="utf-8")
    monkeypatch.setenv("LOADTESTCLIENTID", client_id)

    assert oidc_main(
        [
            "write-oauth-curl-config",
            "--secret-json",
            str(secret_json),
            "--output",
            str(output),
            "--mask-output",
            str(mask_output),
        ]
    ) == 0

    basic = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
    assert secret not in captured.out and basic not in captured.out and client_id not in captured.out
    assert "::add-mask::" not in captured.out
    assert mask_output.read_text(encoding="utf-8").splitlines() == [
        escape_github_command_value(secret),
        basic,
    ]


@pytest.mark.parametrize(
    ("raw_json", "client_id"),
    [
        ("not-json-sensitive-marker", "client"),
        (json.dumps({"secret": "sensitive-marker"}), "client"),
        (json.dumps(""), "client"),
        (json.dumps("sensitive-marker"), None),
        (json.dumps("sensitive-marker"), ""),
    ],
)
def test_oauth_config_rejects_invalid_inputs_without_leaking(
    tmp_path: Path, raw_json: str, client_id: str | None
):
    secret_json = tmp_path / "secret.json"
    output = tmp_path / "curl.conf"
    mask_output = tmp_path / "mask-values.txt"
    secret_json.write_text(raw_json, encoding="utf-8")
    with pytest.raises(OAuthConfigError) as captured:
        write_oauth_curl_config(
            secret_json=secret_json,
            output=output,
            mask_output=mask_output,
            client_id=client_id,
        )
    assert "sensitive-marker" not in str(captured.value)
    assert not output.exists()
    assert not mask_output.exists()
    assert not list(tmp_path.glob(".curl.conf.*.tmp"))


def test_oauth_config_rejects_missing_output_directory_without_partial_file(
    tmp_path: Path,
):
    secret_json = tmp_path / "secret.json"
    secret_json.write_text(json.dumps("synthetic-secret"), encoding="utf-8")
    output = tmp_path / "missing" / "curl.conf"
    mask_output = tmp_path / "missing" / "mask-values.txt"
    with pytest.raises(OAuthConfigError, match="could not be written"):
        write_oauth_curl_config(
            secret_json=secret_json,
            output=output,
            mask_output=mask_output,
            client_id="synthetic-client",
        )
    assert not output.exists()


def test_oauth_config_rejects_non_utf8_surrogate_without_leaking(tmp_path: Path):
    secret_json = tmp_path / "secret.json"
    output = tmp_path / "curl.conf"
    mask_output = tmp_path / "mask-values.txt"
    secret_json.write_text('"\\ud800sensitive-marker"', encoding="utf-8")
    with pytest.raises(OAuthConfigError) as captured:
        write_oauth_curl_config(
            secret_json=secret_json,
            output=output,
            mask_output=mask_output,
            client_id="synthetic-client",
        )
    assert "sensitive-marker" not in str(captured.value)
    assert not output.exists()


def test_oauth_config_removes_atomic_temporary_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    secret_json = tmp_path / "secret.json"
    output = tmp_path / "curl.conf"
    mask_output = tmp_path / "mask-values.txt"
    secret_json.write_text(json.dumps("synthetic-secret"), encoding="utf-8")

    def fail_replace(source: str, destination: Path) -> None:
        raise OSError("synthetic failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OAuthConfigError, match="could not be written"):
        write_oauth_curl_config(
            secret_json=secret_json,
            output=output,
            mask_output=mask_output,
            client_id="synthetic-client",
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".curl.conf.*.tmp"))


def _inject_after_safe_config(workflow_text: str, line: str) -> str:
    marker = "            --config /tmp/genai-oauth-curl.conf \\\n"
    assert marker in workflow_text
    return workflow_text.replace(marker, marker + f"            {line}\n", 1)


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('--user "$A:$B" \\', "curl --user"),
        ('--user="$A:$B" \\', "curl --user"),
        ('--user \\\n              "$A:$B" \\', "curl --user"),
        ('-u "$A:$B" \\', "curl -u"),
        ('-u"$A:$B" \\', "curl -u"),
        ('-u${A}:${B} \\', "curl -u"),
        ('-uVALUE \\', "curl -u"),
        ('-H "Authorization: Basic abc" \\', "Basic Authorization"),
        ('--header "Authorization: Basic abc" \\', "Basic Authorization"),
        ('--header \\\n              "Authorization: Basic abc" \\', "Basic Authorization"),
    ],
)
def test_guardrail_rejects_argv_credentials_while_safe_config_remains(
    line: str, message: str
):
    mutated = _inject_after_safe_config(workflow(), line)
    assert mutated.count("--config /tmp/genai-oauth-curl.conf") == 2
    errors = validate_deploy_workflow(mutated)
    assert any(message in error for error in errors)


@pytest.mark.parametrize(
    ("injection", "message"),
    [
        ('          CLIENT_SECRET="synthetic"\n', "CLIENT_SECRET"),
        ('          echo "$CLIENT_SECRET"\n', "CLIENT_SECRET"),
        ('          printf \'url = "https://example.invalid"\\n\' >> /tmp/genai-oauth-curl.conf\n', "direct shell writes"),
        ('          echo \'url = "https://example.invalid"\' >> /tmp/genai-oauth-curl.conf\n', "direct shell writes"),
        ('          printf synthetic | tee -a /tmp/genai-oauth-curl.conf\n', "direct shell writes"),
        ('          cat <<EOF >> /tmp/genai-oauth-curl.conf\n          url = synthetic\n          EOF\n', "direct shell writes"),
        ('          python - <<\'PY\' > /tmp/genai-oauth-curl.conf\n          PY\n', "direct shell writes"),
    ],
)
def test_guardrail_rejects_shell_secret_or_additional_config_writes(
    injection: str, message: str
):
    mutated = workflow().replace("          FULL_SCOPES=", injection + "          FULL_SCOPES=", 1)
    assert "write-oauth-curl-config" in mutated
    assert mutated.count("--config /tmp/genai-oauth-curl.conf") == 2
    errors = validate_deploy_workflow(mutated)
    assert any(message in error for error in errors)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("          umask 077", "          umask 022", "restrictive umask"),
        ("rm -f /tmp/genai-oauth-curl.conf /tmp/genai-client-secret.json", "rm -f /tmp/genai-oauth-curl.conf", "secret JSON"),
        ("--secret-json /tmp/genai-client-secret.json", "--secret-json secret.json", "temporary secret JSON"),
        ("--output /tmp/genai-oauth-curl.conf", "--output genai-oauth-curl.conf", "temporary curl config"),
    ],
)
def test_guardrail_rejects_weakened_safe_generator_controls(
    old: str, new: str, message: str
):
    mutated = workflow().replace(old, new, 1)
    assert mutated != workflow()
    assert "write-oauth-curl-config" in mutated
    errors = validate_deploy_workflow(mutated)
    assert any(message in error for error in errors)


def test_guardrail_allows_proxy_user_without_confusing_it_with_user():
    mutated = _inject_after_safe_config(workflow(), '--proxy-user "synthetic" \\')
    assert validate_deploy_workflow(mutated) == []


def test_guardrail_rejects_config_write_appended_to_safe_generator_line():
    mutated = workflow().replace(
        "              --output /tmp/genai-oauth-curl.conf",
        "              --output /tmp/genai-oauth-curl.conf; printf synthetic >> /tmp/genai-oauth-curl.conf",
        1,
    )
    errors = validate_deploy_workflow(mutated)
    assert any("direct shell writes" in error for error in errors)


def test_oauth_config_removes_both_outputs_when_mask_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    secret_json = tmp_path / "secret.json"
    output = tmp_path / "curl.conf"
    mask_output = tmp_path / "mask-values.txt"
    secret_json.write_text(json.dumps("synthetic-secret"), encoding="utf-8")
    real_replace = os.replace
    calls = 0

    def fail_second_replace(source: str, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_replace)
    with pytest.raises(OAuthConfigError, match="could not be written"):
        write_oauth_curl_config(
            secret_json=secret_json,
            output=output,
            mask_output=mask_output,
            client_id="synthetic-client",
        )
    assert not output.exists()
    assert not mask_output.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_real_python_helper_has_no_sensitive_logging_calls():
    source = (ROOT / "scripts" / "check_oidc_workflows.py").read_text(
        encoding="utf-8"
    )
    assert validate_sensitive_logging_source(source) == []
    assert 'print(f"::add-mask::' not in source


@pytest.mark.parametrize(
    "statement",
    [
        "print(secret)",
        "print(basic)",
        "print(client_id)",
        'print(f"::add-mask::{mask_value}")',
        "sys.stdout.write(credentials)",
        "sys.stderr.write(authorization)",
        "logging.info(secret)",
        "logging.error(basic)",
        "repr(secret)",
        'raise RuntimeError(f"failed: {secret}")',
    ],
)
def test_sensitive_logging_ast_guard_rejects_dynamic_outputs(statement: str):
    assert validate_sensitive_logging_source(statement)


@pytest.mark.parametrize(
    "source",
    [
        "value = secret\nprint(value)",
        "first = secret\nsecond = first\nprint(second)",
        'payload = {"value": secret}\nprint(payload["value"])',
        "(value,) = (secret,)\nprint(value)",
        "print(value := secret)",
        'value = f"{secret}"\nsys.stderr.write(value)',
        'value = "{}".format(secret)\nlogging.error(value)',
        'value = "%s" % secret\nwarnings.warn(value)',
        "emit = print\nemit(secret)",
        "writer = sys.stdout.write\nwriter(secret)",
        "logger = logging.exception\nlogger(secret)",
        "first = print\nsecond = first\nsecond(secret)",
        'getattr(sys.stderr, "write")(secret)',
        'getattr(logging, "error")(secret)',
        "def emit(value):\n    print(value)\n\nemit(secret)",
        'def prepare(value):\n    return f"{value}"\n\nresult = prepare(secret)\nprint(result)',
        "def intermediate(value):\n    other = value\n    return other\n\nprint(intermediate(secret))",
        "pprint.pprint(secret)",
        "os.write(1, secret.encode())",
        'raise OAuthConfigError(f"{secret}")',
        "error = RuntimeError(secret)",
        "message = secret\nraise RuntimeError(message)",
        "repr(secret)",
    ],
)
def test_sensitive_logging_taint_guard_rejects_derived_outputs(source: str):
    errors = validate_sensitive_logging_source(source)
    assert errors
    assert all("sensitive OAuth" in error or "Sensitive OAuth" in error for error in errors)


@pytest.mark.parametrize(
    "source",
    [
        'print("OIDC workflow guardrails passed")',
        'message = "secret is a word, not data"',
        "ordinary = value\nresult = ordinary",
        'raise OAuthConfigError("OAuth credential input is invalid")',
    ],
)
def test_sensitive_logging_taint_guard_accepts_safe_code(source: str):
    assert validate_sensitive_logging_source(source) == []


@pytest.mark.parametrize(
    "sink",
    [
        'print("constant")',
        'warnings.warn("constant")',
        "traceback.print_exc()",
        'sys.stderr.write("constant")',
    ],
)
def test_sensitive_helpers_reject_every_output_sink(sink: str):
    source = f"def write_oauth_curl_config():\n    {sink}\n"
    assert validate_sensitive_logging_source(source) == [
        "Sensitive OAuth helper functions must not emit output"
    ]


def test_oauth_cli_rejects_constant_output_outside_sanitized_error_handler():
    source = (
        "def main():\n"
        '    print("OAuth curl config generation failed", file=sys.stderr)\n'
    )
    assert validate_sensitive_logging_source(source) == [
        "Python helper must not log sensitive OAuth values"
    ]


def test_oauth_cli_rejects_aliased_output_sink():
    source = "def main():\n    emit = print\n    emit(\"constant\")\n"
    assert validate_sensitive_logging_source(source) == [
        "Python helper must not log sensitive OAuth values"
    ]


def test_oauth_cli_error_is_constant_and_contains_no_sensitive_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    marker = "do-not-log-sensitive-marker"
    secret_json = tmp_path / "secret.json"
    secret_json.write_text(marker, encoding="utf-8")
    monkeypatch.setenv("LOADTESTCLIENTID", marker)
    assert oidc_main(
        [
            "write-oauth-curl-config",
            "--secret-json",
            str(secret_json),
            "--output",
            str(tmp_path / "curl.conf"),
            "--mask-output",
            str(tmp_path / "mask-values.txt"),
        ]
    ) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "OAuth curl config generation failed\n"
    assert marker not in captured.err


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "              --mask-output /tmp/genai-oauth-mask-values.txt",
            "              # mask output removed",
            "protected mask values",
        ),
        (
            "--mask-output /tmp/genai-oauth-mask-values.txt",
            "--mask-output genai-oauth-mask-values.txt",
            "protected mask values",
        ),
        (
            "builtin printf '::add-mask::%s\\n'",
            "printf '::add-mask::%s\\n'",
            "builtin printf",
        ),
        ('test "$mask_count" -eq 2', 'test "$mask_count" -eq 1', "exactly two"),
        ("unset mask_payload", "echo mask retained", "unset"),
    ],
)
def test_guardrail_rejects_weakened_masking_controls(
    old: str, new: str, message: str
):
    mutated = workflow().replace(old, new, 1)
    assert mutated != workflow()
    errors = validate_deploy_workflow(mutated)
    assert any(message in error for error in errors)


@pytest.mark.parametrize(
    "injection",
    [
        "          cat /tmp/genai-oauth-mask-values.txt\n",
        "          value=$(< /tmp/genai-oauth-mask-values.txt)\n",
        "          source /tmp/genai-oauth-mask-values.txt\n",
        "          xargs echo < /tmp/genai-oauth-mask-values.txt\n",
        "          sed -n 1p /tmp/genai-oauth-mask-values.txt\n",
        "          awk '{print}' /tmp/genai-oauth-mask-values.txt\n",
        "          eval \"$(< /tmp/genai-oauth-mask-values.txt)\"\n",
        '          echo "mask=$mask_payload" >> "$GITHUB_ENV"\n',
        '          echo "mask=$mask_payload" >> "$GITHUB_OUTPUT"\n',
    ],
)
def test_guardrail_rejects_external_mask_readers_and_environment_files(
    injection: str,
):
    mutated = workflow().replace("          mask_count=0\n", injection + "          mask_count=0\n", 1)
    errors = validate_deploy_workflow(mutated)
    assert any("exact safe" in error or "exact safe allowlist" in error for error in errors)


@pytest.mark.parametrize(
    "command",
    [
        "head /tmp/genai-oauth-mask-values.txt",
        "tail /tmp/genai-oauth-mask-values.txt",
        "cp /tmp/genai-oauth-mask-values.txt /tmp/copy",
        "install /tmp/genai-oauth-mask-values.txt /tmp/copy",
        "tee /tmp/copy < /tmp/genai-oauth-mask-values.txt",
        "dd if=/tmp/genai-oauth-mask-values.txt",
        "base64 /tmp/genai-oauth-mask-values.txt",
        "python3 -c 'open(\"/tmp/genai-oauth-mask-values.txt\")'",
        "perl -ne 'print' /tmp/genai-oauth-mask-values.txt",
        "ruby -e 'File.read(ARGV[0])' /tmp/genai-oauth-mask-values.txt",
        "openssl base64 -in /tmp/genai-oauth-mask-values.txt",
        "readarray values < /tmp/genai-oauth-mask-values.txt",
        "mapfile values < /tmp/genai-oauth-mask-values.txt",
        "exec 3< /tmp/genai-oauth-mask-values.txt",
        "while read -r other; do :; done < /tmp/genai-oauth-mask-values.txt",
        "value=$(< /tmp/genai-oauth-mask-values.txt)",
        "while read -r other; do :; done < <(grep . /tmp/genai-oauth-mask-values.txt)",
        "grep . /tmp/genai-oauth-mask-values.txt | builtin printf '%s\\n'",
        "run_external_reader",
        "MASK_FILE=/tmp/genai-oauth-mask-values.txt",
        "ls -l /tmp/genai-oauth-mask-values*",
    ],
)
def test_masking_block_allowlist_rejects_every_additional_command(command: str):
    marker = "          mask_count=0\n"
    mutated = workflow().replace(marker, f"          {command}\n{marker}", 1)
    assert marker in mutated
    errors = validate_deploy_workflow(mutated)
    assert "OAuth masking block must match the exact safe command allowlist" in errors


@pytest.mark.parametrize(
    "reference",
    [
        "MASK_FILE=/tmp/genai-oauth-mask-values.txt",
        "echo /tmp/genai-oauth-mask-values.txt >> $GITHUB_OUTPUT",
        "echo /tmp/genai-oauth-mask-values.txt >> $GITHUB_ENV",
        "python3 -c 'open(\"/tmp/genai-oauth-mask-values.txt\")'",
        "while read -r x; do :; done < /tmp/genai-oauth-mask-values.txt",
        "artifact_path=/tmp/genai-oauth-mask-values.txt",
    ],
)
def test_mask_file_reference_allowlist_rejects_uses_outside_masking_block(
    reference: str,
):
    mutated = workflow() + f"\n# synthetic step mutation\n{reference}\n"
    errors = validate_deploy_workflow(mutated)
    assert "OAuth mask file references must match the exact safe allowlist" in errors


def test_guardrail_rejects_missing_immediate_sensitive_file_cleanup():
    mutated = workflow().replace(
        "          rm -f /tmp/genai-oauth-mask-values.txt /tmp/genai-client-secret.json\n",
        "          echo sensitive files retained\n",
        1,
    )
    errors = validate_deploy_workflow(mutated)
    assert any("before OAuth" in error for error in errors)


def test_guardrail_rejects_missing_immediate_curl_config_cleanup():
    mutated = workflow().replace(
        "          rm -f /tmp/genai-oauth-curl.conf\n          FULL_TOKEN=",
        "          echo curl config retained\n          FULL_TOKEN=",
        1,
    )
    errors = validate_deploy_workflow(mutated)
    assert any("immediately after OAuth" in error for error in errors)


def test_guardrail_rejects_mask_file_missing_from_trap():
    mutated = workflow().replace(
        "            rm -f /tmp/genai-oauth-mask-values.txt\n",
        "            echo mask file retained\n",
        1,
    )
    errors = validate_deploy_workflow(mutated)
    assert any("trap must remove mask" in error for error in errors)


def test_guardrail_rejects_mask_file_missing_from_final_cleanup():
    marker = "          rm -f /tmp/genai-oauth-mask-values.txt\n"
    before, separator, after = workflow().rpartition(marker)
    assert separator
    mutated = before + "          echo final mask retained\n" + after
    errors = validate_deploy_workflow(mutated)
    assert any("final cleanup must remove mask" in error for error in errors)
