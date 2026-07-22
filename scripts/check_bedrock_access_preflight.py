#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path
from urllib.parse import urlparse

WORKFLOW = Path(".github/workflows/bedrock-access-preflight.yml")
CONFIG = Path("config/bedrock-access-preflight.json")
READINESS = Path("config/bedrock-access-readiness.json")
POLICY = Path("policies/bedrock-nova-lite-eu-invoke.template.json")
DESIGN = Path("docs/bedrock-access-preflight.md")
ACCESS_DESIGN = Path("docs/bedrock-access-and-iam-design.md")
COPILOT = Path("docs/bedrock-incident-copilot.md")
BACKLOG = Path("docs/well-architected-backlog.md")
REVIEW = Path("docs/well-architected-review.md")
ADR = Path("docs/adr/013-amazon-bedrock-incident-copilot.md")

CONFIG_KEYS = {
    "account_checked",
    "artifact_contains_identifiers",
    "availability_checked",
    "catalog_checked",
    "enabled",
    "environment_configured",
    "execution_authorized",
    "inference_authorized",
    "inference_profile_checked",
    "inference_profile_id",
    "inference_tested",
    "iam_runtime_checked",
    "logs_contain_identifiers",
    "model_id",
    "oidc_role_configured",
    "retention_days",
    "source_region",
    "status",
    "workflow_enabled",
}
FALSE_KEYS = CONFIG_KEYS - {
    "inference_profile_id",
    "model_id",
    "retention_days",
    "source_region",
    "status",
}
INPUTS = {
    "confirm_no_inference",
    "confirm_read_only",
    "confirm_synthetic_lab",
    "inference_profile_id",
    "model_id",
    "source_region",
}
ALLOWED_AWS_COMMANDS = {
    "aws bedrock get-foundation-model",
    "aws bedrock get-inference-profile",
    "aws bedrock list-foundation-models",
    "aws bedrock list-inference-profiles",
    "aws sts get-caller-identity",
}
ALLOWED_AWS_INVOCATIONS = {
    (
        "aws",
        "sts",
        "get-caller-identity",
        "--no-cli-pager",
        "--output",
        "json",
    ),
    (
        "aws",
        "bedrock",
        "list-foundation-models",
        "--region",
        "eu-west-1",
        "--no-cli-pager",
        "--output",
        "json",
    ),
    (
        "aws",
        "bedrock",
        "get-foundation-model",
        "--model-identifier",
        "amazon.nova-lite-v1:0",
        "--region",
        "eu-west-1",
        "--no-cli-pager",
        "--output",
        "json",
    ),
    (
        "aws",
        "bedrock",
        "list-inference-profiles",
        "--region",
        "eu-west-1",
        "--no-cli-pager",
        "--output",
        "json",
    ),
    (
        "aws",
        "bedrock",
        "get-inference-profile",
        "--inference-profile-identifier",
        "eu.amazon.nova-lite-v1:0",
        "--region",
        "eu-west-1",
        "--no-cli-pager",
        "--output",
        "json",
    ),
}
ERROR_CATEGORIES = {
    "identity_check_failed",
    "foundation_models_list_failed",
    "foundation_model_get_failed",
    "inference_profiles_list_failed",
    "inference_profile_get_failed",
}
OFFICIAL_HOSTS = {"docs.aws.amazon.com", "aws.amazon.com", "docs.github.com"}


def fail(control: str) -> None:
    raise SystemExit(f"Bedrock access preflight control failed: {control}")


def require(condition: bool, control: str) -> None:
    if not condition:
        fail(control)


def read(root: Path, relative: Path) -> str:
    path = root / relative
    require(path.is_file(), f"missing {relative}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail(f"unreadable {relative}")


def load(root: Path, relative: Path) -> dict[str, object]:
    try:
        value = json.loads(read(root, relative))
    except json.JSONDecodeError:
        fail(f"valid JSON: {relative}")
    require(type(value) is dict, f"JSON object: {relative}")
    return value


def strip_fences(document: str) -> str:
    output: list[str] = []
    active: tuple[str, int] | None = None
    opening = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\r\n]*(?:\r\n|\r|\n)?$")
    for line in document.splitlines(keepends=True):
        ending = re.search(r"(?:\r\n|\r|\n)$", line)
        if active is None:
            match = opening.fullmatch(line)
            if match:
                marker = match.group(1)
                active = (marker[0], len(marker))
                output.append(ending.group(0) if ending else "")
            else:
                output.append(line)
            continue
        closing = re.compile(
            rf"^ {{0,3}}{re.escape(active[0])}{{{active[1]},}}[ \t]*(?:\r\n|\r|\n)?$"
        )
        if closing.fullmatch(line):
            active = None
        output.append(ending.group(0) if ending else "")
    require(active is None, "unterminated fenced code block")
    return "".join(output)


def section(document: str, start: str, end: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(start)}\s*$\n(.*?)(?=^{re.escape(end)}\s*$)", document
    )
    require(match is not None, f"workflow section {start}")
    return match.group(1)


def mapping_keys(block: str, indent: int) -> set[str]:
    result = set()
    for line in block.splitlines():
        if len(line) - len(line.lstrip(" ")) == indent:
            match = re.match(r"\s*([a-zA-Z0-9_-]+):", line)
            if match:
                result.add(match.group(1))
    return result


def shell_lines(workflow: str) -> list[str]:
    lines: list[str] = []
    in_run = False
    run_indent = 0
    heredoc_end: str | None = None
    for raw in workflow.splitlines():
        indent = len(raw) - len(raw.lstrip(" "))
        if not in_run:
            match = re.match(r"^(\s*)run:\s*\|\s*$", raw)
            if match:
                in_run = True
                run_indent = len(match.group(1))
            continue
        if raw.strip() and indent <= run_indent:
            in_run = False
            heredoc_end = None
            continue
        line = raw[run_indent + 2 :] if len(raw) >= run_indent + 2 else ""
        if heredoc_end is not None:
            if line.strip() == heredoc_end:
                heredoc_end = None
            continue
        heredoc = re.search(r"<<-?['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if heredoc:
            heredoc_end = heredoc.group(1)
        lines.append(line)
    return lines


def shell_tokens(line: str) -> list[str]:
    try:
        return shlex.split(line, comments=True, posix=True)
    except ValueError:
        fail("valid static shell syntax")


def validate_static_shell(workflow: str) -> None:
    lines = shell_lines(workflow)
    commands: list[str] = []
    invocations: list[tuple[str, ...]] = []
    for line in lines:
        tokens = shell_tokens(line)
        if not tokens:
            continue
        executable = tokens
        if executable[:1] == ["!"]:
            executable = executable[1:]
        if (
            executable[:1] in (["eval"], ["source"], ["."])
            or executable[:2] in (["command", "eval"], ["builtin", "eval"])
            or (executable[:1] in (["bash"], ["sh"]) and "-c" in executable[1:])
            or (executable[:1] in (["bash"], ["sh"]) and "<<" in line)
        ):
            fail("dynamic shell execution is forbidden")
        if re.match(r"^\s*alias(?:\s|$)", line) or re.match(
            r"^\s*(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{", line
        ) and re.search(r"\baws\b", line):
            fail("dynamic AWS command is forbidden")
        if re.match(r"^\s*\$\(", line):
            fail("dynamic shell execution is forbidden")
        if re.match(r"^\s*[A-Za-z_][A-Za-z0-9_]*=\([^)]*\baws\b", line):
            fail("dynamic AWS command is forbidden")
        if re.match(r'^\s*["\']?\$\{?[!A-Za-z_]', line):
            fail("dynamic AWS command is forbidden")
        aws_match = re.match(
            r"^\s*aws\s+(sts\s+get-caller-identity|bedrock\s+(?:list-foundation-models|get-foundation-model|list-inference-profiles|get-inference-profile))\b",
            line,
        )
        if re.search(r"(?:^|[;&|!]\s*)aws(?:\s|$)", line):
            if aws_match is None or "$(" in line or "`" in line:
                fail("dynamic AWS command is forbidden")
            commands.append("aws " + re.sub(r"\s+", " ", aws_match.group(1)))
            try:
                redirect = tokens.index(">")
            except ValueError:
                fail("AWS command arguments are not allowed")
            invocation = tuple(tokens[:redirect])
            require(
                invocation in ALLOWED_AWS_INVOCATIONS,
                "AWS command arguments are not allowed",
            )
            invocations.append(invocation)
        elif re.search(r"\baws\b", line) and (
            "$" in line or "(" in line or re.match(r"^\s*[A-Za-z_].*\{", line)
        ):
            fail("dynamic AWS command is forbidden")
    require(set(commands) == ALLOWED_AWS_COMMANDS, "exact read-only AWS commands")
    require(len(commands) == len(ALLOWED_AWS_COMMANDS), "exact read-only AWS commands")
    require(
        set(invocations) == ALLOWED_AWS_INVOCATIONS
        and len(invocations) == len(ALLOWED_AWS_INVOCATIONS),
        "AWS command arguments are not allowed",
    )


def validate_workflow(workflow: str) -> None:
    on_block = section(workflow, "on:", "permissions:")
    require(
        mapping_keys(on_block, 2) == {"workflow_dispatch"},
        "exclusive workflow_dispatch trigger",
    )
    require(mapping_keys(on_block, 6) == INPUTS, "exact workflow inputs")
    for name in INPUTS:
        input_match = re.search(
            rf"(?ms)^      {re.escape(name)}:\s*$\n(.*?)(?=^      [a-zA-Z0-9_-]+:|^permissions:)",
            workflow,
        )
        require(input_match is not None, f"input {name}")
        body = input_match.group(1)
        require("required: true" in body, f"required input {name}")
    for name in ("confirm_no_inference", "confirm_read_only", "confirm_synthetic_lab"):
        body = re.search(
            rf"(?ms)^      {name}:\s*$\n(.*?)(?=^      [a-zA-Z0-9_-]+:|^permissions:)",
            workflow,
        ).group(1)
        require("type: boolean" in body, f"boolean confirmation {name}")
    for name, value in {
        "source_region": "eu-west-1",
        "model_id": "amazon.nova-lite-v1:0",
        "inference_profile_id": "eu.amazon.nova-lite-v1:0",
    }.items():
        body = re.search(
            rf"(?ms)^      {name}:\s*$\n(.*?)(?=^      [a-zA-Z0-9_-]+:|^permissions:)",
            workflow,
        ).group(1)
        require(
            f"default: {value}" in body and "type: string" in body,
            f"exact input {name}",
        )

    permissions = section(workflow, "permissions:", "jobs:")
    require(
        mapping_keys(permissions, 2) == {"contents", "id-token"},
        "minimum GitHub permissions",
    )
    require(
        "  id-token: write" in permissions and "  contents: read" in permissions,
        "OIDC permissions",
    )
    require(
        "environment: bedrock-access-preflight" in workflow, "protected Environment"
    )
    require("if: github.ref == 'refs/heads/main'" in workflow, "main-only execution")
    require(
        "secrets.AWS_BEDROCK_PREFLIGHT_ROLE_ARN" in workflow, "Environment role secret"
    )
    require(
        not re.search(r"arn:(?:aws|aws-us-gov|aws-cn):", workflow, re.IGNORECASE),
        "no hardcoded ARN",
    )
    require(
        not re.search(r"(?<![A-Za-z0-9])\d{12}(?![A-Za-z0-9])", workflow),
        "no account ID",
    )
    require(
        not re.search(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", workflow),
        "no static access key",
    )
    require(
        not re.search(
            r"aws-(?:access-key-id|secret-access-key|session-token)\s*:",
            workflow,
            re.IGNORECASE,
        ),
        "no static credential fields",
    )
    require(
        "aws-actions/configure-aws-credentials@v6.2.2" in workflow,
        "approved OIDC action",
    )
    require("mask-aws-account-id: true" in workflow, "masked AWS account ID")
    require("unset-current-credentials: true" in workflow, "unset existing credentials")
    require("aws-region: eu-west-1" in workflow, "exact AWS region")
    for variable, value in {
        "CONFIRM_NO_INFERENCE": "true",
        "CONFIRM_READ_ONLY": "true",
        "CONFIRM_SYNTHETIC_LAB": "true",
        "SOURCE_REGION": "eu-west-1",
        "MODEL_ID": "amazon.nova-lite-v1:0",
        "INFERENCE_PROFILE_ID": "eu.amazon.nova-lite-v1:0",
    }.items():
        require(
            f'test "${variable}" = "{value}"' in workflow,
            f"closed validation {variable}",
        )
    require("set -euo pipefail" in workflow, "strict shell mode")
    require("set +x" in workflow and "set -x" not in workflow, "shell tracing disabled")
    require("umask 077" in workflow, "private temporary permissions")
    require(
        workflow.count(
            'work_dir="$(mktemp -d "${RUNNER_TEMP}/bedrock-preflight.XXXXXX")"'
        )
        == 1,
        "secure temporary directory",
    )
    require(
        workflow.count('raw_dir="${work_dir}/raw"') == 1
        and workflow.count('candidate="${work_dir}/candidate.json"') == 1,
        "raw files must remain under the secure temporary directory",
    )
    require(
        len(re.findall(r"(?m)^\s*raw_dir=", workflow)) == 1
        and len(re.findall(r"(?m)^\s*candidate=", workflow)) == 1,
        "raw files must remain under the secure temporary directory",
    )
    require(
        workflow.count('mkdir -p "$raw_dir"') == 1
        and not re.search(r"(?m)^\s*ln\s+-s(?:\s|$)", workflow)
        and "../" not in workflow,
        "raw files must remain under the secure temporary directory",
    )
    require("trap cleanup EXIT" in workflow, "raw temporary cleanup trap")
    require(
        workflow.count('cleanup() { rm -rf "$work_dir"; }') == 1
        and workflow.count('rm -rf "$work_dir"') == 1,
        "raw temporary cleanup",
    )
    require("scripts/sanitize_bedrock_preflight.py" in workflow, "sanitizer invocation")
    require("$GITHUB_STEP_SUMMARY" not in workflow, "no step summary evidence")
    require("$GITHUB_OUTPUT" not in workflow, "no GitHub output evidence")
    require("$GITHUB_ENV" not in workflow, "no GitHub environment evidence")
    require(
        not re.search(r"(?m)^\s*(?:env|printenv)(?:\s|$)", workflow),
        "no environment dump",
    )
    require(not re.search(r"(?m)^\s*tee(?:\s|$)", workflow), "no raw tee")
    require(
        not re.search(r"(?m)\bcat\s+.*(?:stderr|raw_dir)", workflow),
        "no raw error output",
    )
    require(
        "--debug" not in workflow
        and "AWS_DEBUG" not in workflow
        and "ACTIONS_STEP_DEBUG" not in workflow,
        "debug disabled",
    )
    require(
        "--endpoint-url" not in workflow and "--no-verify-ssl" not in workflow,
        "AWS endpoint and TLS controls",
    )
    forbidden_aws_environment = (
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CONFIG_FILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "credential_process",
        "source_profile",
    )
    require(
        not any(name in workflow for name in forbidden_aws_environment),
        "manual AWS credential configuration is forbidden",
    )

    validate_static_shell(workflow)
    forbidden = (
        "bedrock-runtime",
        "invoke-model",
        "converse-stream",
        "converse",
        "apply-guardrail",
        "aws iam",
        "aws organizations",
        "aws cloudformation",
        "aws lambda",
        "aws s3",
        "aws logs",
        " create-",
        " update-",
        " delete-",
        " put-",
        " tag-",
        " untag-",
    )
    lowered = workflow.lower()
    require(
        not any(token in lowered for token in forbidden), "no runtime or write command"
    )
    for command_line in re.findall(r"(?m)^\s*aws .*?$", workflow):
        require(
            re.search(r'>\s*"\$raw_dir/[a-z_]+\.json"', command_line) is not None
            and re.search(r'2>\s*"\$raw_dir/[a-z_]+\.stderr"', command_line) is not None
            and "--output json" in command_line,
            "raw AWS stdout and stderr redirected",
        )
    require(workflow.count(".stderr") == 5, "exact raw error files")
    require(
        all(f'fail_aws "{category}"' in workflow for category in ERROR_CATEGORIES),
        "fixed AWS error categories",
    )
    require(
        len(re.findall(r'fail_aws "[a-z_]+"', workflow)) == len(ERROR_CATEGORIES),
        "fixed AWS error categories",
    )
    require(
        'fail_aws() { printf \'%s\\n\' "$1" >&2; exit 1; }' in workflow,
        "sanitized AWS error handler",
    )
    upload_steps = re.findall(r"actions/upload-artifact@[^\s]+", workflow)
    require(upload_steps == ["actions/upload-artifact@v4"], "single artifact upload")
    require(
        "name: bedrock-access-preflight-evidence" in workflow, "fixed artifact name"
    )
    require(
        "path: bedrock-preflight-evidence.json" in workflow, "sanitized artifact only"
    )
    require("if-no-files-found: error" in workflow, "artifact missing failure")
    retention = re.search(r"retention-days:\s*(\d+)", workflow)
    require(
        retention is not None and 1 <= int(retention.group(1)) <= 7,
        "artifact retention",
    )
    uses = set(re.findall(r"(?m)^\s*(?:-\s*)?uses:\s*([^\s]+)", workflow))
    require(
        uses
        == {
            "actions/checkout@v7",
            "actions/upload-artifact@v4",
            "aws-actions/configure-aws-credentials@v6.2.2",
        },
        "exact workflow actions",
    )


def validate_config(config: dict[str, object]) -> None:
    require(set(config) == CONFIG_KEYS, "exact preflight configuration keys")
    require(config["status"] == "proposed-disabled", "preflight status")
    require(config["source_region"] == "eu-west-1", "preflight source region")
    require(config["model_id"] == "amazon.nova-lite-v1:0", "preflight model ID")
    require(
        config["inference_profile_id"] == "eu.amazon.nova-lite-v1:0",
        "preflight profile ID",
    )
    require(
        type(config["retention_days"]) is int and 1 <= config["retention_days"] <= 7,
        "preflight retention",
    )
    for key in FALSE_KEYS:
        require(config[key] is False, f"preflight {key}")


def validate_existing_controls(root: Path) -> None:
    readiness = load(root, READINESS)
    checklist = readiness.get("readiness_checklist")
    require(type(checklist) is list and len(checklist) == 16, "readiness checklist")
    require(
        all(
            type(step) is dict
            and step.get("completed") is False
            and step.get("evidence") is None
            and step.get("verified_at") is None
            for step in checklist
        ),
        "readiness remains pending",
    )
    for key in (
        "iam_policy_applied",
        "account_access_checked",
        "account_access_verified",
        "inference_authorized",
    ):
        require(readiness.get(key) is False, f"readiness {key}")
    policy = load(root, POLICY)
    require(
        policy.get("metadata")
        == {
            "directive": "DO_NOT_APPLY",
            "human_review_required": True,
            "status": "disabled",
        },
        "inert runtime policy",
    )
    rendered = json.dumps(policy, sort_keys=True)
    require(rendered.count('"bedrock:InvokeModel"') == 2, "runtime action unchanged")
    require(
        "InvokeModelWithResponseStream" not in rendered and "*" not in rendered,
        "runtime policy remains minimum",
    )


def validate_documents(root: Path) -> None:
    documents = {
        path: strip_fences(read(root, path))
        for path in (DESIGN, ACCESS_DESIGN, COPILOT, BACKLOG, REVIEW, ADR)
    }
    design = documents[DESIGN]
    normalized_design = re.sub(r"\s+", " ", design)
    urls = re.findall(r"https?://[^)\s]+", design)
    require(len(urls) >= 8, "official source records")
    for value in urls:
        parsed = urlparse(value)
        require(
            parsed.scheme == "https"
            and parsed.hostname in OFFICIAL_HOSTS
            and parsed.username is None
            and parsed.password is None,
            "official source URL",
        )
    for phrase in (
        "2026-07-22T09:06:50Z",
        "Environment",
        "AWS_BEDROCK_PREFLIGHT_ROLE_ARN",
        "NO-GO PARA INFERENCIA BEDROCK REAL",
        "not production-ready",
        "no demuestra acceso runtime",
    ):
        require(phrase in normalized_design, f"documentation {phrase}")
    require(
        "bedrock-access-preflight.md" in documents[ACCESS_DESIGN],
        "access design preflight link",
    )
    require(
        "bedrock-access-preflight.md" in documents[COPILOT], "Copilot preflight link"
    )
    require(
        "WA-032" in documents[BACKLOG] and "WA-032" in documents[REVIEW],
        "WA-032 tracking",
    )
    require("- **Estado:** Proposed" in documents[ADR], "ADR-013 remains Proposed")


def run_guardrail(root: Path) -> None:
    root = root.resolve()
    validate_workflow(read(root, WORKFLOW))
    validate_config(load(root, CONFIG))
    validate_existing_controls(root)
    validate_documents(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    run_guardrail(args.root)
    print("Bedrock access preflight controls passed.")


if __name__ == "__main__":
    main()
