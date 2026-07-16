#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / ".github/workflows/deploy-ephemeral.yml"
DESTROY = ROOT / ".github/workflows/destroy-ephemeral.yml"
OIDC_PREFLIGHT = ROOT / ".github/workflows/aws-oidc-preflight.yml"
AWS_PERFORMANCE = ROOT / ".github/workflows/aws-performance-ephemeral.yml"
BOOTSTRAP = ROOT / "bootstrap/github-oidc-role.yml"
OIDC_WORKFLOWS = (OIDC_PREFLIGHT, AWS_PERFORMANCE, DEPLOY, DESTROY)
OIDC_ACTION_REPOSITORY = "aws-actions/configure-aws-credentials"
OIDC_ACTION_MINIMUM_VERSION = (6, 2, 2)
# The unprefixed form is also an official tag style and is emitted by Dependabot.
OIDC_ACTION_VERSION_PATTERN = re.compile(
    r"(?P<prefix>v?)(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)"
)


class OAuthConfigError(RuntimeError):
    """A stable error that never includes credential material."""


def _step_uses(workflow: str) -> list[tuple[str, str]]:
    """Return real step-level uses values and their step bodies."""
    lines = workflow.splitlines()
    result: list[tuple[str, str]] = []
    position = 0
    while position < len(lines):
        steps_match = re.match(r"^(?P<indent> *)steps:\s*(?:#.*)?$", lines[position])
        if steps_match is None:
            position += 1
            continue
        steps_indent = len(steps_match.group("indent"))
        position += 1
        while position < len(lines):
            line = lines[position]
            if not line.strip() or line.lstrip().startswith("#"):
                position += 1
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= steps_indent:
                break
            step_match = re.match(r"^(?P<indent> *)-\s*(?P<value>.*)$", line)
            if step_match is None:
                position += 1
                continue
            step_indent = len(step_match.group("indent"))
            if step_indent <= steps_indent:
                position += 1
                continue
            start = position
            position += 1
            while position < len(lines):
                candidate = lines[position]
                if candidate.strip() and not candidate.lstrip().startswith("#"):
                    candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                    if candidate_indent <= steps_indent or (
                        candidate_indent == step_indent
                        and re.match(r"^ *-\s*", candidate)
                    ):
                        break
                position += 1
            block_lines = lines[start:position]
            inline_uses = re.fullmatch(r"uses:\s*(.+?)\s*", step_match.group("value"))
            if inline_uses is not None:
                result.append(
                    (_yaml_scalar(inline_uses.group(1)), "\n".join(block_lines))
                )
            for block_line in block_lines[1:]:
                uses_match = re.match(
                    rf"^ {{{step_indent + 2}}}uses:\s*(.+?)\s*$", block_line
                )
                if uses_match is not None:
                    result.append(
                        (_yaml_scalar(uses_match.group(1)), "\n".join(block_lines))
                    )
    return result


def _yaml_scalar(value: str) -> str:
    value = re.sub(r"\s+#.*$", "", value.strip())
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _is_oidc_credential_action_candidate(uses: str) -> bool:
    identifier = uses.split("@", 1)[0].rstrip("/")
    last_component = identifier.rsplit("/", 1)[-1]
    normalized = re.sub(r"[-_.]", "", last_component.lower())
    return normalized == "configureawscredentials"


def validate_oidc_credential_actions(workflows: dict[Path | str, str]) -> list[str]:
    """Validate the official credential action and its coherent semver policy."""
    errors: list[str] = []
    references: list[str] = []

    for path, workflow in workflows.items():
        label = str(path)
        candidates = [
            (uses, body)
            for uses, body in _step_uses(workflow)
            if _is_oidc_credential_action_candidate(uses)
        ]
        if not candidates:
            errors.append(f"{label}: OIDC credential action is required")
            continue
        alternative_exists = any(
            "@" not in uses
            or uses.rsplit("@", 1)[0] != OIDC_ACTION_REPOSITORY
            for uses, _ in candidates
        )
        if alternative_exists:
            errors.append(
                f"{label}: OIDC credential action must use the official repository"
            )
            continue
        if len(candidates) != 1:
            errors.append(
                f"{label}: OIDC credential action must appear exactly once per workflow"
            )
            continue
        uses, step_body = candidates[0]
        for token, message in (
            ("role-to-assume:", "OIDC credential action requires role-to-assume"),
            ("aws-region:", "OIDC credential action requires aws-region"),
            ("allowed-account-ids:", "OIDC credential action requires allowed-account-ids"),
        ):
            if token not in step_body:
                errors.append(f"{label}: {message}")
        if any(
            token in step_body.lower()
            for token in ("aws-access-key-id:", "aws-secret-access-key:", "aws-session-token:")
        ):
            errors.append(f"{label}: static AWS credential configuration is forbidden")
        _, reference = uses.rsplit("@", 1)
        version_match = OIDC_ACTION_VERSION_PATTERN.fullmatch(reference)
        if version_match is None:
            errors.append(
                f"{label}: OIDC credential action must use a canonical full semantic version"
            )
            continue
        version = tuple(
            int(version_match.group(component))
            for component in ("major", "minor", "patch")
        )
        if version[0] != 6:
            errors.append(f"{label}: OIDC credential action major must be 6")
            continue
        if version < OIDC_ACTION_MINIMUM_VERSION:
            errors.append(
                f"{label}: OIDC credential action version must be at least 6.2.2"
            )
            continue
        references.append(reference)

    if len(references) == len(workflows) and len(set(references)) != 1:
        errors.append("OIDC credential action version must be consistent across workflows")
    return errors


def escape_github_command_value(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _write_protected_atomic(output: Path, content: bytes) -> None:
    descriptor = -1
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        temporary = None
        os.chmod(output, 0o600, follow_symlinks=False)
    except (OSError, ValueError) as exc:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        raise OAuthConfigError("OAuth protected output could not be written") from exc


def write_oauth_curl_config(
    *, secret_json: Path, output: Path, mask_output: Path, client_id: str | None
) -> None:
    try:
        raw_secret = secret_json.read_text(encoding="utf-8")
        secret = json.loads(raw_secret)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OAuthConfigError("OAuth credential input is invalid") from exc
    if not isinstance(client_id, str) or not client_id:
        raise OAuthConfigError("OAuth client ID is unavailable")
    if not isinstance(secret, str) or not secret:
        raise OAuthConfigError("OAuth client secret is invalid")

    try:
        basic = base64.b64encode(
            f"{client_id}:{secret}".encode("utf-8")
        ).decode("ascii")
    except UnicodeError as exc:
        raise OAuthConfigError("OAuth credentials are not valid UTF-8 data") from exc
    config_content = f'header = "Authorization: Basic {basic}"\n'.encode("ascii")
    mask_content = (
        f"{escape_github_command_value(secret)}\n"
        f"{escape_github_command_value(basic)}\n"
    ).encode("utf-8")
    try:
        _write_protected_atomic(output, config_content)
        _write_protected_atomic(mask_output, mask_content)
    except OAuthConfigError:
        for path in (output, mask_output):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


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


def _normalized_shell(workflow: str) -> str:
    return re.sub(r"\\\r?\n[ \t]*", " ", workflow)


def _curl_arguments(workflow: str) -> list[str]:
    normalized = _normalized_shell(workflow)
    return [
        match.group(1)
        for match in re.finditer(
            r"(?m)(?:^|[($;])\s*curl\s+([^\n]*)",
            normalized,
        )
    ]


def _validate_masking_allowlist(workflow: str, smoke: str) -> list[str]:
    errors: list[str] = []

    def normalized_lines(content: str) -> list[str]:
        return [
            re.sub(r"[ \t]+", " ", line.strip())
            for line in _normalized_shell(content).splitlines()
        ]

    generator = (
        'LOADTESTCLIENTID="$LOADTESTCLIENTID" '
        "python3 scripts/check_oidc_workflows.py write-oauth-curl-config "
        "--secret-json /tmp/genai-client-secret.json "
        "--output /tmp/genai-oauth-curl.conf "
        "--mask-output /tmp/genai-oauth-mask-values.txt"
    )
    cleanup = "rm -f /tmp/genai-oauth-mask-values.txt /tmp/genai-client-secret.json"
    expected_block = [
        generator,
        "mask_count=0",
        "while IFS= read -r mask_payload; do",
        'test -n "$mask_payload"',
        "builtin printf '::add-mask::%s\\n' \"$mask_payload\"",
        "mask_count=$((mask_count + 1))",
        "done < /tmp/genai-oauth-mask-values.txt",
        "unset mask_payload",
        'test "$mask_count" -eq 2',
        "unset mask_count",
        cleanup,
    ]
    lines = normalized_lines(smoke)
    try:
        start = lines.index(generator)
        end = lines.index(cleanup, start) + 1
    except ValueError:
        errors.append("OAuth masking block must match the exact safe command allowlist")
    else:
        actual = [line for line in lines[start:end] if line and not line.startswith("#")]
        if actual != expected_block:
            errors.append("OAuth masking block must match the exact safe command allowlist")

    expected_references = [
        "rm -f /tmp/genai-oauth-mask-values.txt",
        "rm -f /tmp/.genai-oauth-mask-values.txt.*.tmp",
        generator,
        "done < /tmp/genai-oauth-mask-values.txt",
        cleanup,
        "rm -f /tmp/genai-oauth-mask-values.txt",
        "rm -f /tmp/.genai-oauth-mask-values.txt.*.tmp",
    ]
    actual_references = [
        line
        for line in normalized_lines(workflow)
        if "genai-oauth-mask-values" in line
    ]
    if actual_references != expected_references:
        errors.append("OAuth mask file references must match the exact safe allowlist")
    return errors


def validate_sensitive_logging_source(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["OIDC helper source must be valid Python"]
    sensitive_terms = (
        "secret",
        "basic",
        "client_id",
        "credential",
        "authorization",
        "mask_value",
        "mask_payload",
        "token",
    )
    sink_names = {
        "print",
        "sys.stdout.write",
        "sys.stderr.write",
        "logging.debug",
        "logging.info",
        "logging.warning",
        "logging.warn",
        "logging.error",
        "logging.exception",
        "logging.critical",
        "warnings.warn",
        "pprint.pprint",
        "traceback.print_exc",
        "traceback.print_exception",
        "traceback.print_stack",
        "os.write",
    }
    protected_helpers = {
        "_write_protected_atomic",
        "write_oauth_curl_config",
        "escape_github_command_value",
    }
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    summaries: dict[str, tuple[set[int], set[int]]] = {
        name: (set(), set()) for name in functions
    }

    def dotted_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent else None
        return None

    def sensitive_name(name: str) -> bool:
        lowered = name.lower()
        return any(term in lowered for term in sensitive_terms)

    def target_names(target: ast.AST) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.Tuple, ast.List)):
            return {name for item in target.elts for name in target_names(item)}
        if isinstance(target, (ast.Attribute, ast.Subscript)):
            root = target.value
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            return {root.id} if isinstance(root, ast.Name) else set()
        return set()

    def call_arguments(call: ast.Call) -> list[ast.AST]:
        return [*call.args, *(keyword.value for keyword in call.keywords)]

    def sink_name(call: ast.Call, aliases: dict[str, str]) -> str | None:
        direct = dotted_name(call.func)
        if direct in aliases:
            direct = aliases[direct]
        if direct in sink_names:
            return direct
        if (
            isinstance(call.func, ast.Call)
            and dotted_name(call.func.func) == "getattr"
            and len(call.func.args) >= 2
            and isinstance(call.func.args[1], ast.Constant)
            and isinstance(call.func.args[1].value, str)
        ):
            receiver = dotted_name(call.func.args[0])
            candidate = f"{receiver}.{call.func.args[1].value}"
            return candidate if candidate in sink_names else None
        return None

    def analyze_statements(
        statements: list[ast.stmt],
        initial_taint: set[str],
        *,
        function_name: str | None,
        record: bool,
    ) -> tuple[set[str], bool, list[tuple[int, int, str]]]:
        tainted = set(initial_taint)
        aliases: dict[str, str] = {}
        findings: list[tuple[int, int, str]] = []
        return_tainted = False

        def add(node: ast.AST, message: str) -> None:
            item = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0), message)
            if item not in findings:
                findings.append(item)

        def expr_tainted(node: ast.AST | None) -> bool:
            if node is None or isinstance(node, ast.Constant):
                return False
            if isinstance(node, ast.Name):
                return node.id in tainted or sensitive_name(node.id)
            if isinstance(node, ast.Attribute):
                return sensitive_name(node.attr) or expr_tainted(node.value)
            if isinstance(node, ast.NamedExpr):
                value_tainted = expr_tainted(node.value)
                if value_tainted:
                    tainted.update(target_names(node.target))
                return value_tainted
            if isinstance(node, ast.Call):
                arguments = call_arguments(node)
                direct = dotted_name(node.func)
                if direct and sensitive_name(direct):
                    return True
                if direct in summaries and direct in functions:
                    parameters = list(functions[direct].args.args)
                    by_name = {item.arg: index for index, item in enumerate(parameters)}
                    actual: dict[int, ast.AST] = {
                        index: argument for index, argument in enumerate(node.args)
                    }
                    actual.update(
                        {
                            by_name[keyword.arg]: keyword.value
                            for keyword in node.keywords
                            if keyword.arg in by_name
                        }
                    )
                    return_indices, _ = summaries[direct]
                    if any(
                        index in actual and expr_tainted(actual[index])
                        for index in return_indices
                    ):
                        return True
                return expr_tainted(node.func) or any(expr_tainted(item) for item in arguments)
            return any(expr_tainted(child) for child in ast.iter_child_nodes(node))

        def visit_statement(statement: ast.stmt) -> None:
            nonlocal return_tainted
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return
            if isinstance(statement, ast.Assign):
                direct = dotted_name(statement.value)
                resolved = aliases.get(direct, direct) if direct else None
                names = {name for target in statement.targets for name in target_names(target)}
                if resolved in sink_names:
                    for name in names:
                        aliases[name] = resolved
                elif direct in aliases:
                    for name in names:
                        aliases[name] = aliases[direct]
                if expr_tainted(statement.value):
                    tainted.update(names)
            elif isinstance(statement, ast.AnnAssign):
                if expr_tainted(statement.value):
                    tainted.update(target_names(statement.target))
            elif isinstance(statement, (ast.For, ast.AsyncFor)):
                if expr_tainted(statement.iter):
                    tainted.update(target_names(statement.target))
            elif isinstance(statement, ast.With):
                for item in statement.items:
                    if expr_tainted(item.context_expr) and item.optional_vars:
                        tainted.update(target_names(item.optional_vars))
            elif isinstance(statement, ast.Return):
                return_tainted = return_tainted or expr_tainted(statement.value)
            elif isinstance(statement, ast.Raise) and statement.exc is not None:
                if expr_tainted(statement.exc):
                    add(statement, "Python helper exceptions must not interpolate sensitive OAuth values")

            for node in ast.walk(statement):
                if not isinstance(node, ast.Call):
                    continue
                sink = sink_name(node, aliases)
                arguments = call_arguments(node)
                sensitive_output = any(expr_tainted(item) for item in arguments)
                if sink == "os.write":
                    fd_sensitive = bool(
                        node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value in {1, 2}
                    )
                    sensitive_output = fd_sensitive and any(
                        expr_tainted(item) for item in node.args[1:]
                    )
                if sink and function_name in protected_helpers:
                    add(node, "Sensitive OAuth helper functions must not emit output")
                elif sink and sensitive_output:
                    add(node, "Python helper must not log sensitive OAuth values")
                if dotted_name(node.func) == "repr" and sensitive_output:
                    add(node, "Python helper must not render sensitive OAuth values")
                called_name = dotted_name(node.func) or ""
                if (
                    called_name.endswith(("Error", "Exception"))
                    and sensitive_output
                ):
                    add(
                        node,
                        "Python helper exceptions must not interpolate sensitive OAuth values",
                    )
                called = dotted_name(node.func)
                if called in summaries and called in functions:
                    parameters = list(functions[called].args.args)
                    by_name = {item.arg: index for index, item in enumerate(parameters)}
                    actual = {index: argument for index, argument in enumerate(node.args)}
                    actual.update(
                        {
                            by_name[keyword.arg]: keyword.value
                            for keyword in node.keywords
                            if keyword.arg in by_name
                        }
                    )
                    _, sink_indices = summaries[called]
                    if any(
                        index in actual and expr_tainted(actual[index])
                        for index in sink_indices
                    ):
                        add(node, "Python helper must not log sensitive OAuth values")

            for child in ast.iter_child_nodes(statement):
                if isinstance(child, ast.stmt):
                    visit_statement(child)

        previous: tuple[frozenset[str], tuple[tuple[str, str], ...]] | None = None
        while previous != (frozenset(tainted), tuple(sorted(aliases.items()))):
            previous = (frozenset(tainted), tuple(sorted(aliases.items())))
            for statement in statements:
                visit_statement(statement)
        return tainted, return_tainted, findings if record else findings

    changed = True
    while changed:
        changed = False
        for name, function in functions.items():
            parameters = list(function.args.args)
            return_indices: set[int] = set()
            sink_indices: set[int] = set()
            for index, parameter in enumerate(parameters):
                _, returns, findings = analyze_statements(
                    function.body,
                    {parameter.arg},
                    function_name=name,
                    record=False,
                )
                if returns:
                    return_indices.add(index)
                if findings:
                    sink_indices.add(index)
            summary = (return_indices, sink_indices)
            if summary != summaries[name]:
                summaries[name] = summary
                changed = True

    findings: list[tuple[int, int, str]] = []
    _, _, module_findings = analyze_statements(
        tree.body, set(), function_name=None, record=True
    )
    findings.extend(module_findings)
    for name, function in functions.items():
        _, _, function_findings = analyze_statements(
            function.body, set(), function_name=name, record=True
        )
        findings.extend(function_findings)

    parent: dict[ast.AST, ast.AST] = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    main = functions.get("main")
    if main:
        main_aliases: dict[str, str] = {}
        main_nodes = sorted(
            ast.walk(main),
            key=lambda item: (getattr(item, "lineno", 0), getattr(item, "col_offset", 0)),
        )
        for node in main_nodes:
            if isinstance(node, ast.Assign):
                direct = dotted_name(node.value)
                resolved = main_aliases.get(direct, direct) if direct else None
                if resolved in sink_names:
                    for target in node.targets:
                        for name in target_names(target):
                            main_aliases[name] = resolved
            if not isinstance(node, ast.Call) or sink_name(node, main_aliases) is None:
                continue
            allowed = (
                dotted_name(node.func) == "print"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "OAuth curl config generation failed"
                and len(node.keywords) == 1
                and node.keywords[0].arg == "file"
                and dotted_name(node.keywords[0].value) == "sys.stderr"
            )
            ancestor = parent.get(node)
            while ancestor is not None and not isinstance(ancestor, ast.ExceptHandler):
                ancestor = parent.get(ancestor)
            allowed = allowed and isinstance(ancestor, ast.ExceptHandler) and (
                dotted_name(ancestor.type) == "OAuthConfigError"
            )
            if not allowed:
                findings.append(
                    (node.lineno, node.col_offset, "Python helper must not log sensitive OAuth values")
                )

    return [message for _, _, message in sorted(set(findings))]


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
    errors.extend(validate_oidc_credential_actions({"deploy workflow": workflow}))
    required_tokens = {
        "environment: aws-ephemeral": "aws-ephemeral Environment is required",
        "github.ref == 'refs/heads/main'": "workflow must run only from main",
        "VALIDATE-GENAI-SHELL-AND-DESTROY": "explicit GenAI confirmation is required",
        "DEPLOY-AND-DESTROY": "explicit legacy confirmation is required",
        "group: aws-ephemeral-${{ github.repository }}": "protected concurrency group is required",
        "cancel-in-progress: false": "concurrent executions must not be cancelled",
        "required reviewers": "required-reviewer governance warning is required",
        "write-oauth-curl-config": "safe OAuth credential generator is required",
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
    curl_arguments = _curl_arguments(workflow)
    for arguments in curl_arguments:
        require(
            re.search(r"(?:^|\s)--user(?=$|[=\s])", arguments) is None,
            "curl --user is forbidden globally",
        )
        require(
            re.search(r"(?:^|\s)-u(?:$|\s|\S+)", arguments) is None,
            "curl -u and attached -uVALUE are forbidden globally",
        )
    require(
        re.search(r"authorization\s*:\s*basic", _normalized_shell(lower)) is None,
        "Basic Authorization must not be constructed in workflow shell",
    )
    require("client_secret" not in lower, "CLIENT_SECRET shell variables are forbidden")
    smoke = by_id.get("genai_smoke", "")
    errors.extend(_validate_masking_allowlist(workflow, smoke))
    for token, message in {
        "--output json > /tmp/genai-client-secret.json": "client secret must be captured as protected JSON",
        "python3 scripts/check_oidc_workflows.py write-oauth-curl-config": "safe OAuth config subcommand is required",
        "--secret-json /tmp/genai-client-secret.json": "safe subcommand must read the temporary secret JSON",
        "--output /tmp/genai-oauth-curl.conf": "safe subcommand must write the temporary curl config",
        "--mask-output /tmp/genai-oauth-mask-values.txt": "safe subcommand must write protected mask values",
        "umask 077": "curl config requires restrictive umask",
        "--config /tmp/genai-oauth-curl.conf": "OAuth calls must use curl config",
        "trap cleanup_temporaries EXIT": "OAuth config requires trap cleanup",
        "rm -f /tmp/genai-oauth-curl.conf": "OAuth config must be removed by the trap",
        "rm -f /tmp/genai-oauth-curl.conf /tmp/genai-client-secret.json": "secret JSON must be removed by the trap",
        "rm -f /tmp/genai-oauth-mask-values.txt": "mask values must be removed by the trap",
        "while IFS= read -r mask_payload; do": "mask values must be read with Bash builtins",
        "builtin printf '::add-mask::%s\\n' \"$mask_payload\"": "mask values must use builtin printf",
        'test "$mask_count" -eq 2': "exactly two mask values are required",
        "unset mask_payload": "mask payload must be unset",
    }.items():
        require(token in smoke, message)
    require(smoke.count("--config /tmp/genai-oauth-curl.conf") == 2, "both OAuth calls must use curl config")
    require("/tmp/genai-oauth-curl.conf" in temp_cleanup_block, "final cleanup must remove curl config")
    require(
        "rm -f /tmp/genai-oauth-curl.conf /tmp/genai-client-secret.json" in temp_cleanup_block,
        "final cleanup must remove secret JSON",
    )
    for token, message in {
        "/tmp/genai-oauth-mask-values.txt": "final cleanup must remove mask values",
        "/tmp/.genai-oauth-mask-values.txt.*.tmp": "final cleanup must remove atomic mask temporaries",
    }.items():
        require(token in temp_cleanup_block, message)
    normalized_smoke = _normalized_shell(smoke)
    trap_definition = smoke.split("trap cleanup_temporaries EXIT", 1)[0]
    require(
        "/tmp/genai-oauth-mask-values.txt" in trap_definition
        and "/tmp/.genai-oauth-mask-values.txt.*.tmp" in trap_definition,
        "trap must remove mask values and atomic temporaries",
    )
    generator_position = normalized_smoke.find("write-oauth-curl-config")
    mask_position = normalized_smoke.find("while IFS= read -r mask_payload; do")
    immediate_cleanup_position = normalized_smoke.find(
        "rm -f /tmp/genai-oauth-mask-values.txt /tmp/genai-client-secret.json"
    )
    first_oauth_position = normalized_smoke.find("curl --silent")
    second_oauth_position = normalized_smoke.find("curl --silent", first_oauth_position + 1)
    config_cleanup_position = normalized_smoke.find(
        "rm -f /tmp/genai-oauth-curl.conf", second_oauth_position
    )
    token_parse_position = normalized_smoke.find("FULL_TOKEN=")
    require(
        -1 < generator_position < mask_position < immediate_cleanup_position < first_oauth_position,
        "masking and sensitive input cleanup must finish before OAuth",
    )
    require(
        -1 < second_oauth_position < config_cleanup_position < token_parse_position,
        "curl config must be removed immediately after OAuth responses",
    )
    require("export mask_payload" not in normalized_smoke, "mask payload must not be exported")
    require("$GITHUB_ENV" not in smoke and "$GITHUB_OUTPUT" not in smoke, "OAuth mask values must not use GitHub environment files")
    config_lines = [
        line
        for line in _normalized_shell(smoke).splitlines()
        if "/tmp/genai-oauth-curl.conf" in line
    ]
    for line in config_lines:
        safe_generator = re.fullmatch(
            r'\s*LOADTESTCLIENTID="\$LOADTESTCLIENTID"\s+'
            r"python3 scripts/check_oidc_workflows\.py write-oauth-curl-config\s+"
            r"--secret-json /tmp/genai-client-secret\.json\s+"
            r"--output /tmp/genai-oauth-curl\.conf\s+"
            r"--mask-output /tmp/genai-oauth-mask-values\.txt\s*",
            line,
        )
        allowed = bool(safe_generator) or (
            "--config /tmp/genai-oauth-curl.conf" in line
            or re.search(r"\brm\s+-f\b", line) is not None
        )
        require(allowed, "direct shell writes to curl config are forbidden")
        require(
            re.search(r"(?:^|[;&|])\s*(?:printf|echo|cat|tee|python\s+-)\b", line)
            is None,
            "direct shell writes to curl config are forbidden",
        )
    required_temporaries = (
        "/tmp/genai-oauth-curl.conf",
        "/tmp/genai-client-secret.json",
        "/tmp/genai-oauth-mask-values.txt",
        "/tmp/.genai-oauth-curl.conf.*.tmp",
        "/tmp/.genai-oauth-mask-values.txt.*.tmp",
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


def validate_repository() -> int:
    errors: list[str] = []
    for path in (*OIDC_WORKFLOWS, BOOTSTRAP):
        if not path.is_file():
            errors.append(f"Missing required file: {path}")
    if errors:
        print("\n".join(errors))
        return 1

    deploy = DEPLOY.read_text(encoding="utf-8")
    destroy = DESTROY.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    workflow_contents = {
        path: path.read_text(encoding="utf-8") for path in OIDC_WORKFLOWS
    }
    errors.extend(validate_oidc_credential_actions(workflow_contents))
    errors.extend(f"{DEPLOY}: {error}" for error in validate_deploy_workflow(deploy))
    source = Path(__file__).read_text(encoding="utf-8")
    errors.extend(
        f"{Path(__file__)}: {error}"
        for error in validate_sensitive_logging_source(source)
    )
    errors.extend(f"{BOOTSTRAP}: {error}" for error in validate_bootstrap_policy(bootstrap))

    for source, content in ((DESTROY, destroy),):
        for token in (
            "workflow_dispatch:",
            "id-token: write",
            "contents: read",
            "environment: aws-ephemeral",
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


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        return validate_repository()

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    oauth = commands.add_parser(
        "write-oauth-curl-config",
        help="Write a protected curl config for OAuth client credentials",
    )
    oauth.add_argument("--secret-json", type=Path, required=True)
    oauth.add_argument("--output", type=Path, required=True)
    oauth.add_argument("--mask-output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        write_oauth_curl_config(
            secret_json=args.secret_json,
            output=args.output,
            mask_output=args.mask_output,
            client_id=os.environ.get("LOADTESTCLIENTID"),
        )
    except OAuthConfigError:
        print("OAuth curl config generation failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
