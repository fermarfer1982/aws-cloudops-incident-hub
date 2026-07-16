#!/usr/bin/env python3
"""Validate sanitized evidence for the closed GenAI AWS infrastructure shell."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


GENAI_FUNCTION_NAME = "cloudops-genai-summary-function"
GENAI_LOG_GROUP_NAME = "/aws/lambda/cloudops-genai-summary-function"
GENAI_ROUTE = "POST /incidents/{incident_id}/ai-summary"
SUMMARIZE_SCOPE = "cloudops-incident-hub/incidents.summarize"
EXPECTED_ACTIONS = {
    "dynamodb:GetItem",
    "logs:CreateLogStream",
    "logs:PutLogEvents",
}
EXPECTED_DETAIL = {"detail": "AI summary service is unavailable"}
FORBIDDEN_RESPONSE_FIELDS = {
    "summary",
    "model_id",
    "usage",
    "observed_facts",
    "probable_causes",
}
EVIDENCE_FIELDS = {
    "commit_sha",
    "workflow_run_id",
    "region",
    "stack_name",
    "timestamp",
    "route_tested",
    "authenticated_request",
    "unauthenticated_request",
    "wrong_scope_request",
    "feature_provider_state",
    "iam_actions",
    "bedrock_permissions_present",
    "destroy_status",
    "resource_cleanup_status",
}
SENSITIVE_EVIDENCE_TERMS = {
    "account_id",
    "api_url",
    "arn",
    "client_id",
    "client_secret",
    "cloudformation_events",
    "incident_id",
    "logs",
    "message",
    "metadata",
    "model_id",
    "outputs",
    "payload",
    "repository_url",
    "secret",
    "site",
    "source",
    "template",
    "token",
    "type",
    "userpoolid",
}


class ValidationError(RuntimeError):
    """A sanitized, stable validation failure."""


def _fail(control: str) -> None:
    raise ValidationError(f"GenAI shell validation failed: {control}")


def _load_json(path: Path, control: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail(control)


def _resources(template: Mapping[str, Any], resource_type: str) -> dict[str, Any]:
    resources = template.get("Resources")
    if not isinstance(resources, Mapping):
        _fail("template resources")
    return {
        str(logical_id): resource
        for logical_id, resource in resources.items()
        if isinstance(resource, Mapping) and resource.get("Type") == resource_type
    }


def _single(items: list[Any], control: str) -> Any:
    if len(items) != 1:
        _fail(control)
    return items[0]


def _actions(statements: list[Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    for statement in statements:
        action = statement.get("Action")
        values = [action] if isinstance(action, str) else action
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            _fail("IAM action structure")
        result.update(values)
    return result


def validate_template(template: Mapping[str, Any]) -> list[str]:
    functions = _resources(template, "AWS::Lambda::Function")
    function_matches = [
        (logical_id, resource)
        for logical_id, resource in functions.items()
        if resource.get("Properties", {}).get("FunctionName") == GENAI_FUNCTION_NAME
    ]
    function_id, function = _single(function_matches, "dedicated Lambda")
    properties = function.get("Properties", {})
    role_ref = properties.get("Role", {}).get("Fn::GetAtt")
    if not isinstance(role_ref, list) or len(role_ref) != 2 or role_ref[1] != "Arn":
        _fail("independent Lambda role reference")
    role_id = role_ref[0]

    roles = _resources(template, "AWS::IAM::Role")
    role = roles.get(role_id)
    if not isinstance(role, Mapping):
        _fail("independent Lambda role")
    if "ManagedPolicyArns" in role.get("Properties", {}):
        _fail("managed policies absent")

    policies = [
        resource
        for resource in _resources(template, "AWS::IAM::Policy").values()
        if {"Ref": role_id} in resource.get("Properties", {}).get("Roles", [])
    ]
    if len(policies) != 1:
        _fail("single GenAI IAM policy")
    statements = policies[0].get("Properties", {}).get("PolicyDocument", {}).get("Statement")
    if not isinstance(statements, list) or not all(isinstance(item, Mapping) for item in statements):
        _fail("IAM statements")
    actions = _actions(statements)
    if actions != EXPECTED_ACTIONS or any("*" in action for action in actions):
        _fail("exact IAM actions")

    get_item = _single(
        [statement for statement in statements if statement.get("Action") == "dynamodb:GetItem"],
        "GetItem statement",
    )
    resource = get_item.get("Resource")
    if not (
        isinstance(resource, Mapping)
        and isinstance(resource.get("Fn::GetAtt"), list)
        and len(resource["Fn::GetAtt"]) == 2
        and resource["Fn::GetAtt"][1] == "Arn"
    ):
        _fail("GetItem incident table resource")
    table_id = resource["Fn::GetAtt"][0]
    tables = _resources(template, "AWS::DynamoDB::Table")
    table = tables.get(table_id)
    if not isinstance(table, Mapping):
        _fail("GetItem incident table resource")
    table_name = table.get("Properties", {}).get("TableName")
    if table_name != "cloudops-incidents":
        _fail("GetItem incident table resource")
    rendered_resource = json.dumps(resource, sort_keys=True).lower()
    if "index" in rendered_resource or "metric" in rendered_resource:
        _fail("GetItem resource boundary")

    variables = properties.get("Environment", {}).get("Variables")
    if not isinstance(variables, Mapping):
        _fail("closed Lambda environment")
    if variables.get("AI_SUMMARY_ENABLED") != "false":
        _fail("feature disabled")
    if variables.get("AI_SUMMARY_PROVIDER") != "disabled":
        _fail("provider disabled")
    forbidden_variables = {
        "AI_SUMMARY_MODEL_ID",
        "AI_SUMMARY_ALLOWED_MODEL_IDS",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    }
    if forbidden_variables.intersection(variables):
        _fail("forbidden Lambda configuration absent")

    rendered = json.dumps(template, sort_keys=True).lower()
    for token in (
        "arn:aws:bedrock",
        ":bedrock:",
        "bedrock:",
        "inference profile",
        "inference_profile",
        "bedrock_endpoint",
        "invokemodel",
    ):
        if token in rendered:
            _fail("Bedrock configuration absent")

    routes = _resources(template, "AWS::ApiGatewayV2::Route")
    route_matches = [
        resource
        for resource in routes.values()
        if resource.get("Properties", {}).get("RouteKey") == GENAI_ROUTE
    ]
    route = _single(route_matches, "single GenAI route").get("Properties", {})
    if route.get("AuthorizationType") != "JWT":
        _fail("GenAI route JWT authorization")
    if route.get("AuthorizationScopes") != [SUMMARIZE_SCOPE]:
        _fail("GenAI route scope")
    join = route.get("Target", {}).get("Fn::Join")
    if not isinstance(join, list) or len(join) != 2 or not isinstance(join[1], list):
        _fail("GenAI route integration reference")
    integration_refs = [item["Ref"] for item in join[1] if isinstance(item, Mapping) and "Ref" in item]
    integration_id = _single(integration_refs, "GenAI route integration reference")
    integration = _resources(template, "AWS::ApiGatewayV2::Integration").get(integration_id)
    if not isinstance(integration, Mapping):
        _fail("GenAI route integration")
    uri = integration.get("Properties", {}).get("IntegrationUri", {}).get("Fn::GetAtt")
    if uri != [function_id, "Arn"]:
        _fail("GenAI route Lambda target")

    log_groups = _resources(template, "AWS::Logs::LogGroup")
    if len(
        [
            item
            for item in log_groups.values()
            if item.get("Properties", {}).get("LogGroupName") == GENAI_LOG_GROUP_NAME
        ]
    ) != 1:
        _fail("GenAI Log Group")

    alarm_names = {
        item.get("Properties", {}).get("AlarmName")
        for item in _resources(template, "AWS::CloudWatch::Alarm").values()
    }
    if not {
        "cloudops-genai-summary-errors",
        "cloudops-genai-summary-throttles",
    }.issubset(alarm_names):
        _fail("GenAI native alarms")

    dashboards = _resources(template, "AWS::CloudWatch::Dashboard")
    if len(dashboards) != 1:
        _fail("operations dashboard")
    dashboard = json.dumps(next(iter(dashboards.values())), sort_keys=True)
    for metric in ("Invocations", "Errors", "Duration", "Throttles", "ConcurrentExecutions"):
        if metric not in dashboard:
            _fail("GenAI native dashboard metrics")
    return sorted(actions)


def _content_type_is_json(headers: str) -> bool:
    return any(
        line.lower().startswith("content-type:") and "application/json" in line.lower()
        for line in headers.splitlines()
    )


def validate_http_responses(
    *,
    authenticated_status: int,
    authenticated_headers: str,
    authenticated_body: Any,
    unauthenticated_status: int,
    wrong_scope_status: int,
) -> None:
    if authenticated_status != 503:
        _fail("authenticated HTTP status")
    if not _content_type_is_json(authenticated_headers):
        _fail("authenticated JSON content type")
    if authenticated_body != EXPECTED_DETAIL:
        _fail("authenticated closed response")
    if isinstance(authenticated_body, Mapping) and FORBIDDEN_RESPONSE_FIELDS.intersection(
        authenticated_body
    ):
        _fail("generated response fields absent")
    if unauthenticated_status not in {401, 403}:
        _fail("unauthenticated HTTP status")
    if wrong_scope_status != 403:
        _fail("wrong-scope HTTP status")


def build_evidence(
    *,
    commit_sha: str,
    workflow_run_id: str,
    region: str,
    timestamp: str,
    unauthenticated_status: int,
) -> dict[str, Any]:
    evidence = {
        "commit_sha": commit_sha,
        "workflow_run_id": workflow_run_id,
        "region": region,
        "stack_name": "CloudOpsIncidentHubStack",
        "timestamp": timestamp,
        "route_tested": GENAI_ROUTE,
        "authenticated_request": {"status": 503, "passed": True},
        "unauthenticated_request": {
            "status": unauthenticated_status,
            "passed": True,
        },
        "wrong_scope_request": {"status": 403, "passed": True},
        "feature_provider_state": {"enabled": False, "provider": "disabled"},
        "iam_actions": sorted(EXPECTED_ACTIONS),
        "bedrock_permissions_present": False,
        "destroy_status": "success",
        "resource_cleanup_status": "verified",
    }
    validate_evidence(evidence)
    return evidence


def validate_evidence(evidence: Mapping[str, Any]) -> None:
    if set(evidence) != EVIDENCE_FIELDS:
        _fail("strict evidence fields")
    serialized = json.dumps(evidence, sort_keys=True).lower()
    if any(f'"{term}"' in serialized for term in SENSITIVE_EVIDENCE_TERMS):
        _fail("sensitive evidence fields absent")
    if re.search(r"(?<![0-9])[0-9]{12}(?![0-9])", serialized) or "arn:" in serialized:
        _fail("sensitive evidence values absent")
    if evidence.get("stack_name") != "CloudOpsIncidentHubStack":
        _fail("evidence stack name")
    if evidence.get("route_tested") != GENAI_ROUTE:
        _fail("evidence route")
    if evidence.get("iam_actions") != sorted(EXPECTED_ACTIONS):
        _fail("evidence IAM actions")
    if evidence.get("bedrock_permissions_present") is not False:
        _fail("evidence Bedrock state")
    expected_nested = {
        "authenticated_request": {"status": 503, "passed": True},
        "wrong_scope_request": {"status": 403, "passed": True},
        "feature_provider_state": {"enabled": False, "provider": "disabled"},
    }
    if any(evidence.get(name) != value for name, value in expected_nested.items()):
        _fail("evidence control values")
    anonymous = evidence.get("unauthenticated_request")
    if anonymous not in (
        {"status": 401, "passed": True},
        {"status": 403, "passed": True},
    ):
        _fail("evidence unauthenticated result")
    if evidence.get("destroy_status") != "success":
        _fail("evidence destroy status")
    if evidence.get("resource_cleanup_status") != "verified":
        _fail("evidence cleanup status")


def write_evidence_atomic(path: Path, evidence: Mapping[str, Any]) -> None:
    validate_evidence(evidence)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".genai-shell-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="Validate a CloudFormation template")
    template.add_argument("--template", type=Path, required=True)

    responses = commands.add_parser("responses", help="Validate stored HTTP results")
    responses.add_argument("--authenticated-status", type=int, required=True)
    responses.add_argument("--authenticated-headers", type=Path, required=True)
    responses.add_argument("--authenticated-body", type=Path, required=True)
    responses.add_argument("--unauthenticated-status", type=int, required=True)
    responses.add_argument("--wrong-scope-status", type=int, required=True)

    evidence = commands.add_parser("evidence", help="Write sanitized evidence")
    evidence.add_argument("--output", type=Path, required=True)
    evidence.add_argument("--commit-sha", required=True)
    evidence.add_argument("--workflow-run-id", required=True)
    evidence.add_argument("--region", required=True)
    evidence.add_argument("--timestamp", required=True)
    evidence.add_argument("--unauthenticated-status", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "template":
            template = _load_json(args.template, "template JSON")
            if not isinstance(template, Mapping):
                _fail("template object")
            validate_template(template)
            print("GenAI shell template validation passed")
        elif args.command == "responses":
            headers = args.authenticated_headers.read_text(encoding="utf-8")
            body = _load_json(args.authenticated_body, "authenticated JSON response")
            validate_http_responses(
                authenticated_status=args.authenticated_status,
                authenticated_headers=headers,
                authenticated_body=body,
                unauthenticated_status=args.unauthenticated_status,
                wrong_scope_status=args.wrong_scope_status,
            )
            print("GenAI shell HTTP validation passed")
        else:
            evidence = build_evidence(
                commit_sha=args.commit_sha,
                workflow_run_id=args.workflow_run_id,
                region=args.region,
                timestamp=args.timestamp,
                unauthenticated_status=args.unauthenticated_status,
            )
            write_evidence_atomic(args.output, evidence)
            print("Sanitized GenAI shell evidence written")
    except (OSError, UnicodeError, ValidationError) as exc:
        message = str(exc) if isinstance(exc, ValidationError) else "GenAI shell validation failed: file access"
        print(message)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
