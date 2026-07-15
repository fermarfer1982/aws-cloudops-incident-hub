#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / ".github/workflows/deploy-ephemeral.yml"
DESTROY = ROOT / ".github/workflows/destroy-ephemeral.yml"
BOOTSTRAP = ROOT / "bootstrap/github-oidc-role.yml"


def _contains_automatic_trigger(workflow: str) -> bool:
    lines = workflow.splitlines()
    try:
        start = lines.index("on:") + 1
    except ValueError:
        return True
    block = []
    for line in lines[start:]:
        if line and not line.startswith(" "):
            break
        block.append(line)
    keys = [
        match.group(1)
        for line in block
        if (match := re.match(r"^  ([A-Za-z_]+):", line))
    ]
    return keys != ["workflow_dispatch"]


def _top_level_block(workflow: str, name: str) -> list[str]:
    lines = workflow.splitlines()
    try:
        start = lines.index(f"{name}:") + 1
    except ValueError:
        return []
    result: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith(" "):
            break
        result.append(line)
    return result


def _step_blocks(workflow: str) -> list[str]:
    lines = workflow.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.startswith("      - name:")
    ]
    return [
        "\n".join(
            lines[
                start : starts[position + 1]
                if position + 1 < len(starts)
                else len(lines)
            ]
        )
        for position, start in enumerate(starts)
    ]


def _step_condition(block: str) -> str:
    match = re.search(r"(?m)^\s+if:\s*(.+)$", block)
    return match.group(1).strip() if match else ""


def _step_id(block: str) -> str:
    match = re.search(r"(?m)^\s+id:\s*([A-Za-z0-9_-]+)\s*$", block)
    return match.group(1) if match else ""


def _profile_condition(block: str, profile: str) -> bool:
    condition = _step_condition(block)
    return (
        "steps.preflight.outcome == 'success'" in condition
        and f"steps.preflight.outputs.profile == '{profile}'" in condition
    )


def _sid_blocks(template: str) -> dict[str, str]:
    lines = template.splitlines()
    starts = [
        (index, match.group(1))
        for index, line in enumerate(lines)
        if (match := re.match(r"^\s+- Sid: ([A-Za-z0-9]+)\s*$", line))
    ]
    return {
        sid: "\n".join(
            lines[start : starts[position + 1][0] if position + 1 < len(starts) else len(lines)]
        )
        for position, (start, sid) in enumerate(starts)
    }


def validate_bootstrap_policy(template: str) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    blocks = _sid_blocks(template)
    lambda_block = blocks.get("VerifyGenAiSummaryFunctionCleanup", "")
    logs_block = blocks.get("VerifyGenAiSummaryLogGroupCleanup", "")
    lambda_arn = (
        "arn:${AWS::Partition}:lambda:${DeploymentRegion}:${AWS::AccountId}:"
        "function:cloudops-genai-summary-function"
    )

    require(bool(lambda_block), "Lambda cleanup statement is required")
    require(
        lambda_block.count("Action: lambda:GetFunction") == 1,
        "Lambda cleanup must allow exactly lambda:GetFunction",
    )
    require(lambda_arn in lambda_block, "Lambda cleanup resource must be the exact function ARN")
    require('Resource: "*"' not in lambda_block, "Lambda cleanup resource must not be wildcard")
    require(bool(logs_block), "Logs cleanup statement is required")
    require(
        logs_block.count("Action: logs:DescribeLogGroups") == 1,
        "Logs cleanup must allow exactly logs:DescribeLogGroups",
    )
    require('Resource: "*"' in logs_block, "DescribeLogGroups requires wildcard resource")

    action_values = re.findall(
        r"(?m)^\s+(?:Action:\s*|-\s+)((?:lambda|logs):[A-Za-z*]+)\s*$",
        template,
    )
    lambda_actions = [action for action in action_values if action.startswith("lambda:")]
    logs_actions = [action for action in action_values if action.startswith("logs:")]
    require(lambda_actions == ["lambda:GetFunction"], "no other Lambda action is allowed")
    require(logs_actions == ["logs:DescribeLogGroups"], "no other Logs action is allowed")
    require(
        "token.actions.githubusercontent.com:aud: sts.amazonaws.com" in template
        and template.count(
            "repo:${GitHubOwner}/${GitHubRepository}:environment:${GitHubEnvironment}"
        )
        == 2,
        "OIDC trust must remain restricted to the GitHub Environment",
    )
    return errors


def validate_deploy_workflow(workflow: str) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(not _contains_automatic_trigger(workflow), "trigger must be exclusively manual")
    permissions = {line.strip() for line in _top_level_block(workflow, "permissions")}
    require("contents: read" in permissions, "permissions.contents must be read")
    require("id-token: write" in permissions, "permissions.id-token must be write")
    required_tokens = {
        "environment: aws-ephemeral": "aws-ephemeral Environment is required",
        "github.ref == 'refs/heads/main'": "workflow must run only from main",
        "VALIDATE-GENAI-SHELL-AND-DESTROY": "explicit GenAI confirmation is required",
        "DEPLOY-AND-DESTROY": "explicit legacy confirmation is required",
        "group: aws-ephemeral-${{ github.repository }}": "protected concurrency group is required",
        "cancel-in-progress: false": "concurrent executions must not be cancelled",
        "aws-actions/configure-aws-credentials@v6.1.0": "OIDC credential action is required",
        "required reviewers": "required-reviewer governance warning is required",
        "::add-mask::$CLIENT_SECRET": "client secret must be masked",
        "::add-mask::$FULL_TOKEN": "full token must be masked",
        "::add-mask::$PARTIAL_TOKEN": "partial token must be masked",
        "cloudops-incident-hub/incidents.read cloudops-incident-hub/incidents.write cloudops-incident-hub/incidents.summarize": "full token scopes are incomplete",
        'PARTIAL_SCOPES="cloudops-incident-hub/incidents.read cloudops-incident-hub/incidents.write"': "partial token scopes are invalid",
        "name: genai-shell-aws-validation-${{ github.run_id }}": "sanitized artifact name is required",
        "path: evidence/genai-shell-validation.json": "artifact must contain only sanitized evidence",
        "retention-days: 7": "artifact retention must be seven days",
        "Remove GenAI validation temporary files": "temporary cleanup step is required",
        "Enforce GenAI validation and cleanup outcomes": "final outcome enforcement is required",
    }
    for token, message in required_tokens.items():
        require(token in workflow, message)
    dispatch = "\n".join(_top_level_block(workflow, "on"))
    require("validation_profile:" in dispatch, "validation_profile input is required")
    require("type: choice" in dispatch, "validation_profile must be a choice")
    require("default: genai-shell" in dispatch, "GenAI profile must be the default")
    options_match = re.search(
        r"validation_profile:.*?options:\s*\n((?:\s+-\s+[^\n]+\n?)+)",
        dispatch,
        re.DOTALL,
    )
    options = re.findall(r"^\s+-\s+([^\s]+)\s*$", options_match.group(1), re.MULTILINE) if options_match else []
    require(options == ["genai-shell", "legacy"], "profile choices must be exact")
    require(workflow.count("VALIDATE-GENAI-SHELL-AND-DESTROY") == 1, "GenAI confirmation must remain exact")
    require(workflow.count("DEPLOY-AND-DESTROY") == 1, "legacy confirmation must remain exact")
    require(
        'test "$RUN_SMOKE_TEST" = "false"' in workflow
        and 'test "$RUN_CHATOPS_TEST" = "false"' in workflow,
        "GenAI preflight must reject both legacy modes",
    )
    require(
        'if [ "$RUN_SMOKE_TEST" != "true" ]' in workflow
        and '[ "$RUN_CHATOPS_TEST" != "true" ]' in workflow,
        "legacy preflight must require at least one legacy mode",
    )
    require(
        "printf 'profile=%s\\n' \"$VALIDATION_PROFILE\" >> \"$GITHUB_OUTPUT\"" in workflow,
        "preflight must publish only the sanitized profile output",
    )

    context_count = workflow.count("-c enable_load_test_client=true")
    require(context_count >= 3, "synth, deploy and destroy must use the M2M context")
    steps = _step_blocks(workflow)
    require(bool(steps) and _step_id(steps[0]) == "preflight", "preflight must be the first step")
    preflight_position = workflow.find("id: preflight")
    for token in ("actions/checkout@", "aws-actions/configure-aws-credentials@", "aws sts ", "cdk synth"):
        position = workflow.find(token)
        require(position > preflight_position, f"preflight must precede {token}")

    by_id = {_step_id(block): block for block in steps if _step_id(block)}
    require("destroy" in by_id, "destroy step id is required")
    require("cleanup" in by_id, "cleanup step id is required")
    require("legacy)" in by_id.get("preflight", ""), "preflight must handle the legacy profile")
    for step_id, block in by_id.items():
        if step_id.startswith("legacy_"):
            require(
                _profile_condition(block, "legacy"),
                f"{step_id} must be explicitly isolated to the legacy profile",
            )
    for step_id in ("iam", "genai_smoke", "evidence", "genai_upload", "temp_cleanup"):
        require(
            step_id in by_id and _profile_condition(by_id[step_id], "genai-shell"),
            f"{step_id} must be explicitly isolated to the GenAI profile",
        )

    legacy_tokens = (
        "filter-log-events",
        "get-log-events",
        "describe-log-streams",
        "logs tail",
        "dlq",
        "aws-ephemeral-evidence-",
        "deployment-metadata",
        "collect failure diagnostics",
        "collect asynchronous processor diagnostics",
    )
    for block in steps:
        lower_block = block.lower()
        if any(token in lower_block for token in legacy_tokens):
            require(
                _profile_condition(block, "legacy"),
                "raw logs, diagnostics and legacy evidence must require successful legacy preflight",
            )
    genai_workflow = "\n".join(
        block
        for block in steps
        if "GenAI" in block or "genai-shell-validation.json" in block
    ).lower()
    for raw_log_command in ("filter-log-events", "get-log-events", "logs tail"):
        require(
            raw_log_command not in genai_workflow,
            "GenAI validation must not download raw logs",
        )
    destroy_steps = [block for block in steps if block.startswith("      - name: Destroy ephemeral stack")]
    cleanup_steps = [block for block in steps if block.startswith("      - name: Verify stack removal")]
    require(
        len(destroy_steps) == 1
        and "if: always()" in destroy_steps[0]
        and "steps.preflight.outcome == 'success'" in destroy_steps[0]
        and "cdk destroy" in destroy_steps[0]
        and "-c enable_load_test_client=true" in destroy_steps[0],
        "destroy must run under always() with matching context",
    )
    require(
        len(cleanup_steps) == 1
        and "if: always()" in cleanup_steps[0]
        and "steps.preflight.outcome == 'success'" in cleanup_steps[0],
        "cleanup must run under always()",
    )
    if destroy_steps and cleanup_steps:
        require(
            workflow.index(destroy_steps[0]) < workflow.index(cleanup_steps[0]),
            "cleanup checks must run after destroy",
        )
    if cleanup_steps:
        cleanup = cleanup_steps[0]
        for token, message in {
            "aws lambda get-function": "cleanup must call Lambda GetFunction",
            "--function-name cloudops-genai-summary-function": "cleanup must use the exact Lambda name",
            "ResourceNotFoundException": "cleanup must accept only Lambda not-found",
            "> /tmp/genai-cleanup-function.json": "GetFunction stdout must remain temporary",
            "2> /tmp/genai-cleanup-function-error.txt": "GetFunction stderr must remain temporary",
            "aws logs describe-log-groups": "cleanup must call DescribeLogGroups",
            "--log-group-name-prefix /aws/lambda/cloudops-genai-summary-function": "cleanup must use the exact Log Group prefix",
            "logGroupName=='/aws/lambda/cloudops-genai-summary-function'": "cleanup must compare the exact Log Group name",
            "GenAI Lambda still exists": "an existing Lambda must fail cleanup",
            "GenAI Lambda absence could not be verified": "Lambda API errors must fail closed",
            "GenAI Log Group still exists": "an existing Log Group must fail cleanup",
            "GenAI Log Group absence could not be verified": "Logs API errors must fail closed",
            "trap cleanup_verification_files EXIT": "cleanup temporaries must be removed",
        }.items():
            require(token in cleanup, message)
        require("AccessDenied" not in cleanup, "AccessDenied must not be treated as absence")
        for forbidden_call in (
            "list-functions",
            "get-function-configuration",
            "filter-log-events",
            "get-log-events",
            "describe-log-streams",
            "logs tail",
        ):
            require(forbidden_call not in cleanup, "cleanup must not read resources or log events broadly")
    require(
        "steps.genai_smoke.outcome" in workflow
        and "steps.iam.outcome" in workflow
        and "steps.evidence.outcome" in workflow
        and "steps.destroy.outcome" in workflow
        and "steps.cleanup.outcome" in workflow,
        "final result must enforce every GenAI validation outcome",
    )

    evidence_block = by_id.get("evidence", "")
    upload_block = by_id.get("genai_upload", "")
    temp_cleanup_block = by_id.get("temp_cleanup", "")
    required_evidence_outcomes = (
        "preflight",
        "synth",
        "deploy",
        "iam",
        "genai_smoke",
        "destroy",
        "cleanup",
    )
    for outcome in required_evidence_outcomes:
        require(
            f"steps.{outcome}.outcome == 'success'" in _step_condition(evidence_block),
            f"evidence must require successful {outcome}",
        )
    require(
        workflow.find("id: destroy") < workflow.find("id: cleanup") < workflow.find("id: evidence") < workflow.find("id: genai_upload") < workflow.find("id: temp_cleanup"),
        "GenAI order must be destroy, cleanup, evidence, upload and temporary cleanup",
    )
    require(
        _profile_condition(upload_block, "genai-shell")
        and "steps.evidence.outcome == 'success'" in _step_condition(upload_block),
        "GenAI upload must require successful evidence in the GenAI profile",
    )
    require(
        "path: evidence/genai-shell-validation.json" in upload_block
        and "path: evidence/\n" not in upload_block
        and "path: evidence/**" not in upload_block,
        "GenAI upload path must be the single sanitized file",
    )
    require(
        "/tmp/genai-cdk-outputs.json" in workflow,
        "GenAI CDK outputs must be temporary",
    )
    require(
        'outputs_file="/tmp/genai-cdk-outputs.json"' in workflow,
        "GenAI deploy outputs must be assigned to the temporary path",
    )
    genai_blocks = "\n".join(
        block for block in steps if "profile == 'genai-shell'" in _step_condition(block)
    )
    require(
        "evidence/cdk-outputs.json" not in genai_blocks,
        "GenAI steps must not use evidence/cdk-outputs.json",
    )

    lower = workflow.lower()
    require("curl --user" not in lower, "curl --user is forbidden globally")
    require(
        re.search(r"(?m)^\s*(?:curl\s+)?-u(?:\s|$)", lower) is None,
        "curl -u is forbidden globally",
    )
    require("authorization: basic" not in lower, "Basic Authorization must not be passed in argv")
    smoke = by_id.get("genai_smoke", "")
    for token, message in {
        "OAUTH_CURL_CONFIG=/tmp/genai-oauth-curl.conf": "temporary curl config is required",
        "umask 077": "curl config requires restrictive umask",
        "chmod 600 /tmp/genai-oauth-curl.conf": "curl config requires mode 600",
        "--config /tmp/genai-oauth-curl.conf": "OAuth calls must use curl config",
        "trap cleanup_temporaries EXIT": "OAuth config requires trap cleanup",
        "rm -f /tmp/genai-oauth-curl.conf": "OAuth config must be removed by the trap",
    }.items():
        require(token in smoke, message)
    require(smoke.count("--config /tmp/genai-oauth-curl.conf") == 2, "both OAuth calls must use curl config")
    require("/tmp/genai-oauth-curl.conf" in temp_cleanup_block, "final cleanup must remove curl config")
    required_temporaries = (
        "/tmp/genai-oauth-curl.conf",
        "/tmp/client-secret.txt",
        "/tmp/cloudops-full-token.json",
        "/tmp/cloudops-partial-token.json",
        "/tmp/genai-cdk-outputs.json",
        "/tmp/genai-event.json",
        "/tmp/genai-create-response.json",
        "/tmp/genai-incidents.json",
        "/tmp/genai-summary-request.json",
        "/tmp/genai-authenticated-headers.txt",
        "/tmp/genai-authenticated-body.json",
        "/tmp/genai-unauthenticated-body.txt",
        "/tmp/genai-wrong-scope-body.txt",
        "/tmp/genai-deployed-template-response.json",
        "/tmp/genai-deployed-template.json",
        "/tmp/genai-cleanup-stack.json",
        "/tmp/genai-cleanup-function.json",
        "/tmp/genai-cleanup-log-groups.json",
        "/tmp/genai-log-metric.json",
        "/tmp/shell-validation-status.env",
        "evidence/genai-shell-validation.json",
        "rmdir evidence",
        "infrastructure/cdk.out",
    )
    for temporary in required_temporaries:
        require(temporary in temp_cleanup_block, f"final cleanup must remove {temporary}")

    enforcement = next((block for block in steps if "Enforce GenAI validation" in block), "")
    require(_step_condition(enforcement) == "always()", "final enforcement must run under always()")
    require("genai-shell)" in enforcement and "legacy)" in enforcement, "enforcement must distinguish profiles")
    require("steps.genai_upload.outcome" in enforcement and "steps.temp_cleanup.outcome" in enforcement, "GenAI enforcement must include upload and cleanup")
    require(
        enforcement.count('test "$outcome" = "success"') == 2,
        "both profiles must reject skipped outcomes",
    )

    forbidden = {
        "aws-access-key-id:": "static AWS access key configuration is forbidden",
        "aws-secret-access-key:": "static AWS secret configuration is forbidden",
        "pull_request_target": "pull_request_target is forbidden",
        "set -x": "shell tracing is forbidden",
        "bedrock-runtime": "Bedrock calls are forbidden",
        "bedrock:invoke": "Bedrock permissions are forbidden",
    }
    for token, message in forbidden.items():
        require(token not in lower, message)
    require(
        re.search(r"(?m)^\s*aws sts get-caller-identity\s*$", workflow) is None,
        "AWS identity must not be printed",
    )

    artifact_blocks = [block for block in steps if block.startswith("      - name: Upload ")]
    sanitized = [block for block in artifact_blocks if "GenAI shell" in block]
    legacy = [block for block in artifact_blocks if "temporary deployment" in block]
    require(len(sanitized) == 1, "exactly one sanitized GenAI artifact step is required")
    require(len(legacy) == 1 and _profile_condition(legacy[0], "legacy"), "legacy artifact must require the legacy profile")
    if sanitized:
        block = sanitized[0].lower()
        path_lines = [line.strip() for line in block.splitlines() if line.strip().startswith("path:")]
        require(path_lines == ["path: evidence/genai-shell-validation.json"], "artifact path must remain strictly sanitized")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in (DEPLOY, DESTROY, BOOTSTRAP):
        if not path.is_file():
            errors.append(f"Missing required file: {path}")
    if errors:
        print("\n".join(errors))
        return 1

    deploy = DEPLOY.read_text(encoding="utf-8")
    destroy = DESTROY.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    errors.extend(f"{DEPLOY}: {error}" for error in validate_deploy_workflow(deploy))
    errors.extend(f"{BOOTSTRAP}: {error}" for error in validate_bootstrap_policy(bootstrap))

    for source, content in ((DESTROY, destroy),):
        for token in (
            "workflow_dispatch:",
            "id-token: write",
            "contents: read",
            "environment: aws-ephemeral",
            "aws-actions/configure-aws-credentials@v6.1.0",
            "allowed-account-ids:",
            "github.ref == 'refs/heads/main'",
            "cancel-in-progress: false",
        ):
            if token not in content:
                errors.append(f"{source}: missing required token: {token}")
        for token in ("aws-access-key-id:", "aws-secret-access-key:", "pull_request_target"):
            if token.lower() in content.lower():
                errors.append(f"{source}: forbidden token found: {token}")

    for token in (
        "token.actions.githubusercontent.com:aud: sts.amazonaws.com",
        "repo:${GitHubOwner}/${GitHubRepository}:environment:${GitHubEnvironment}",
        "Action: sts:AssumeRole",
    ):
        if token not in bootstrap:
            errors.append(f"{BOOTSTRAP}: missing required token: {token}")

    if errors:
        print("OIDC workflow guardrails failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("OIDC workflow guardrails passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
