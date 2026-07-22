from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_bedrock_access_preflight import run_guardrail

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ".github/workflows/bedrock-access-preflight.yml",
    "config/bedrock-access-preflight.json",
    "config/bedrock-access-readiness.json",
    "policies/bedrock-nova-lite-eu-invoke.template.json",
    "docs/bedrock-access-preflight.md",
    "docs/bedrock-access-and-iam-design.md",
    "docs/bedrock-incident-copilot.md",
    "docs/well-architected-backlog.md",
    "docs/well-architected-review.md",
    "docs/adr/013-amazon-bedrock-incident-copilot.md",
    "scripts/check_bedrock_access_preflight.py",
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    for relative in FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def path(root: Path, relative: str) -> Path:
    return root / relative


def replace(root: Path, relative: str, old: str, new: str) -> None:
    target = path(root, relative)
    text = target.read_text(encoding="utf-8")
    assert old in text
    target.write_text(text.replace(old, new), encoding="utf-8")
    assert new in target.read_text(encoding="utf-8")


def rejected(root: Path, control: str) -> None:
    with pytest.raises(SystemExit, match=control):
        run_guardrail(root)


def load(root: Path, relative: str) -> dict:
    return json.loads(path(root, relative).read_text(encoding="utf-8"))


def write(root: Path, relative: str, value: object) -> None:
    path(root, relative).write_text(json.dumps(value), encoding="utf-8")


def test_intact_copy_passes(repository: Path):
    run_guardrail(repository)


@pytest.mark.parametrize(
    ("old", "new", "control"),
    [
        (
            "on:\n  workflow_dispatch:",
            "on:\n  push:\n  workflow_dispatch:",
            "exclusive workflow_dispatch trigger",
        ),
        (
            "on:\n  workflow_dispatch:",
            "on:\n  pull_request:\n  workflow_dispatch:",
            "exclusive workflow_dispatch trigger",
        ),
        (
            "on:\n  workflow_dispatch:",
            "on:\n  schedule:\n  workflow_dispatch:",
            "exclusive workflow_dispatch trigger",
        ),
        (
            "on:\n  workflow_dispatch:",
            "on:\n  workflow_call:\n  workflow_dispatch:",
            "exclusive workflow_dispatch trigger",
        ),
        (
            "on:\n  workflow_dispatch:",
            "on:\n  repository_dispatch:\n  workflow_dispatch:",
            "exclusive workflow_dispatch trigger",
        ),
        (
            "permissions:\n  id-token: write\n  contents: read",
            "permissions:\n  id-token: write\n  contents: write",
            "(?:minimum GitHub permissions|OIDC permissions)",
        ),
        (
            "permissions:\n  id-token: write\n  contents: read",
            "permissions:\n  contents: read",
            "minimum GitHub permissions",
        ),
        (
            "permissions:\n  id-token: write\n  contents: read",
            "permissions:\n  id-token: write",
            "minimum GitHub permissions",
        ),
        (
            "permissions:\n  id-token: write\n  contents: read",
            "permissions:\n  id-token: write\n  contents: read\n  actions: write",
            "minimum GitHub permissions",
        ),
        (
            "environment: bedrock-access-preflight",
            "environment: aws-ephemeral",
            "protected Environment",
        ),
        (
            "environment: bedrock-access-preflight",
            "timeout-minutes: 10",
            "protected Environment",
        ),
        (
            "if: github.ref == 'refs/heads/main'",
            "if: github.ref != ''",
            "main-only execution",
        ),
        (
            "secrets.AWS_BEDROCK_PREFLIGHT_ROLE_ARN",
            "secrets.OTHER_ROLE",
            "Environment role secret",
        ),
        (
            "aws-actions/configure-aws-credentials@v6.2.2",
            "aws-actions/configure-aws-credentials@v5",
            "approved OIDC action",
        ),
        (
            "mask-aws-account-id: true",
            "mask-aws-account-id: false",
            "masked AWS account ID",
        ),
        (
            "unset-current-credentials: true",
            "unset-current-credentials: false",
            "unset existing credentials",
        ),
        ("aws-region: eu-west-1", "aws-region: us-east-1", "exact AWS region"),
        ("set +x", "set -x", "shell tracing disabled"),
        ("trap cleanup EXIT", "true", "raw temporary cleanup trap"),
        ('rm -rf "$work_dir"', "true", "raw temporary cleanup"),
        (
            "python3 scripts/sanitize_bedrock_preflight.py",
            "python3 -m json.tool",
            "sanitizer invocation",
        ),
        (
            "if-no-files-found: error",
            "if-no-files-found: warn",
            "artifact missing failure",
        ),
        ("retention-days: 7", "retention-days: 8", "artifact retention"),
        (
            "name: bedrock-access-preflight-evidence",
            "name: other",
            "fixed artifact name",
        ),
        ("path: bedrock-preflight-evidence.json", "path: .", "sanitized artifact only"),
        (
            "actions/upload-artifact@v4",
            "actions/upload-artifact@v3",
            "single artifact upload",
        ),
        (
            "aws sts get-caller-identity",
            "aws iam list-roles",
            "(?:exact read-only AWS commands|dynamic AWS command is forbidden)",
        ),
        (
            "aws bedrock list-foundation-models",
            "aws bedrock-runtime invoke-model",
            "(?:exact read-only AWS commands|dynamic AWS command is forbidden)",
        ),
        (
            "aws bedrock get-foundation-model",
            "aws bedrock converse",
            "(?:exact read-only AWS commands|dynamic AWS command is forbidden)",
        ),
        (
            "aws bedrock list-inference-profiles",
            "aws organizations list-accounts",
            "(?:exact read-only AWS commands|dynamic AWS command is forbidden)",
        ),
        (
            "aws bedrock get-inference-profile",
            "aws bedrock delete-inference-profile",
            "(?:exact read-only AWS commands|dynamic AWS command is forbidden)",
        ),
        (
            ' > "$raw_dir/identity.json"',
            "",
            "(?:raw AWS stdout and stderr redirected|AWS command arguments are not allowed)",
        ),
        (
            ' --output json > "$raw_dir/models.json"',
            ' > "$raw_dir/models.json"',
            "(?:raw AWS stdout and stderr redirected|AWS command arguments are not allowed)",
        ),
        (
            "set -euo pipefail",
            "printenv\n          set -euo pipefail",
            "no environment dump",
        ),
        (
            "set -euo pipefail",
            "env\n          set -euo pipefail",
            "no environment dump",
        ),
        (
            "set -euo pipefail",
            "tee raw.json\n          set -euo pipefail",
            "no raw tee",
        ),
        (
            "set -euo pipefail",
            "echo data >> $GITHUB_STEP_SUMMARY\n          set -euo pipefail",
            "no step summary evidence",
        ),
        (
            "set -euo pipefail",
            "export AWS_DEBUG=1\n          set -euo pipefail",
            "debug disabled",
        ),
        (
            "unset-current-credentials: true",
            "aws-access-key-id: example\n          aws-secret-access-key: example",
            "no static credential fields",
        ),
        (
            "steps:\n      - name: Check out",
            "steps:\n      - uses: example/action@v1\n      - name: Check out",
            "exact workflow actions",
        ),
        (
            "secrets.AWS_BEDROCK_PREFLIGHT_ROLE_ARN",
            "arn:aws:iam::" + "0" * 12 + ":role/example",
            "(?:Environment role secret|no hardcoded ARN)",
        ),
        (
            "set -euo pipefail",
            "echo " + "0" * 12 + "\n          set -euo pipefail",
            "no account ID",
        ),
        (
            "set -euo pipefail",
            "echo " + "AKIA" + "ABCDEFGHIJKLMNOP\n          set -euo pipefail",
            "no static access key",
        ),
    ],
)
def test_workflow_mutations_fail(repository: Path, old: str, new: str, control: str):
    replace(repository, FILES[0], old, new)
    rejected(repository, control)


@pytest.mark.parametrize(
    "name",
    [
        "confirm_no_inference",
        "confirm_read_only",
        "confirm_synthetic_lab",
        "source_region",
        "model_id",
        "inference_profile_id",
    ],
)
def test_missing_input_fails(repository: Path, name: str):
    replace(repository, FILES[0], f"      {name}:", f"      removed_{name}:")
    rejected(repository, "exact workflow inputs")


@pytest.mark.parametrize(
    "name", ["confirm_no_inference", "confirm_read_only", "confirm_synthetic_lab"]
)
def test_confirmation_must_be_boolean(repository: Path, name: str):
    target = path(repository, FILES[0])
    text = target.read_text()
    start = text.index(f"      {name}:")
    position = text.index("type: boolean", start)
    target.write_text(
        text[:position] + "type: string" + text[position + len("type: boolean") :]
    )
    rejected(repository, f"boolean confirmation {name}")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("source_region", "us-east-1"),
        ("model_id", "amazon.nova-pro-v1:0"),
        ("inference_profile_id", "global.amazon.nova-lite-v1:0"),
    ],
)
def test_closed_values_are_exact(repository: Path, name: str, value: str):
    expected = {
        "source_region": "eu-west-1",
        "model_id": "amazon.nova-lite-v1:0",
        "inference_profile_id": "eu.amazon.nova-lite-v1:0",
    }[name]
    replace(repository, FILES[0], f"default: {expected}", f"default: {value}")
    rejected(repository, f"exact input {name}")


@pytest.mark.parametrize(
    ("variable", "expected", "replacement"),
    [
        ("CONFIRM_NO_INFERENCE", "true", "false"),
        ("CONFIRM_READ_ONLY", "true", "false"),
        ("CONFIRM_SYNTHETIC_LAB", "true", "false"),
        ("SOURCE_REGION", "eu-west-1", "us-east-1"),
        ("MODEL_ID", "amazon.nova-lite-v1:0", "amazon.nova-pro-v1:0"),
        (
            "INFERENCE_PROFILE_ID",
            "eu.amazon.nova-lite-v1:0",
            "us.amazon.nova-lite-v1:0",
        ),
    ],
)
def test_runtime_input_validation_is_closed(
    repository: Path, variable: str, expected: str, replacement: str
):
    replace(
        repository,
        FILES[0],
        f'test "${variable}" = "{expected}"',
        f'test "${variable}" = "{replacement}"',
    )
    rejected(repository, f"closed validation {variable}")


@pytest.mark.parametrize(
    "extra", ["prompt", "payload", "account_id", "role_arn", "endpoint", "client_id"]
)
def test_additional_inputs_fail(repository: Path, extra: str):
    replace(
        repository,
        FILES[0],
        "    inputs:\n",
        f"    inputs:\n      {extra}:\n        required: false\n        type: string\n",
    )
    rejected(repository, "exact workflow inputs")


@pytest.mark.parametrize(
    "key",
    [
        "account_checked",
        "artifact_contains_identifiers",
        "availability_checked",
        "catalog_checked",
        "enabled",
        "environment_configured",
        "execution_authorized",
        "inference_authorized",
        "inference_profile_checked",
        "inference_tested",
        "iam_runtime_checked",
        "logs_contain_identifiers",
        "oidc_role_configured",
        "workflow_enabled",
    ],
)
def test_disabled_configuration_flags_reject_true(repository: Path, key: str):
    data = load(repository, FILES[1])
    data[key] = True
    write(repository, FILES[1], data)
    rejected(repository, f"preflight {key}")


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "missing",
        "wrong_type",
        "retention",
        "region",
        "model",
        "profile",
        "status",
    ],
)
def test_configuration_shape_and_values_fail(repository: Path, mutation: str):
    data = load(repository, FILES[1])
    if mutation == "extra":
        data["extra"] = False
    elif mutation == "missing":
        data.pop("enabled")
    elif mutation == "wrong_type":
        data["enabled"] = 0
    elif mutation == "retention":
        data["retention_days"] = 8
    elif mutation == "region":
        data["source_region"] = "us-east-1"
    elif mutation == "model":
        data["model_id"] = "amazon.nova-pro-v1:0"
    elif mutation == "profile":
        data["inference_profile_id"] = "us.amazon.nova-lite-v1:0"
    else:
        data["status"] = "enabled"
    write(repository, FILES[1], data)
    rejected(repository, "(?:exact preflight configuration keys|preflight)")


@pytest.mark.parametrize(
    "mutation",
    [
        "completed",
        "evidence",
        "timestamp",
        "missing_step",
        "additional_step",
        "iam",
        "checked",
        "verified",
        "authorized",
    ],
)
def test_original_readiness_remains_pending(repository: Path, mutation: str):
    data = load(repository, FILES[2])
    steps = data["readiness_checklist"]
    if mutation == "completed":
        steps[0]["completed"] = True
    elif mutation == "evidence":
        steps[0]["evidence"] = "claimed"
    elif mutation == "timestamp":
        steps[0]["verified_at"] = "2026-07-22T00:00:00Z"
    elif mutation == "missing_step":
        steps.pop()
    elif mutation == "additional_step":
        steps.append(dict(steps[-1]))
    elif mutation == "iam":
        data["iam_policy_applied"] = True
    elif mutation == "checked":
        data["account_access_checked"] = True
    elif mutation == "verified":
        data["account_access_verified"] = True
    else:
        data["inference_authorized"] = True
    write(repository, FILES[2], data)
    rejected(repository, "readiness")


@pytest.mark.parametrize(
    "mutation", ["apply", "enabled", "no_review", "streaming", "wildcard"]
)
def test_runtime_template_remains_inert(repository: Path, mutation: str):
    data = load(repository, FILES[3])
    if mutation == "apply":
        data["metadata"]["directive"] = "APPLY"
    elif mutation == "enabled":
        data["metadata"]["status"] = "enabled"
    elif mutation == "no_review":
        data["metadata"]["human_review_required"] = False
    elif mutation == "streaming":
        data["policy_template"]["Statement"][0]["Action"] = (
            "bedrock:InvokeModelWithResponseStream"
        )
    else:
        data["policy_template"]["Statement"][0]["Resource"] = "*"
    write(repository, FILES[3], data)
    rejected(repository, "(?:inert runtime policy|runtime)")


@pytest.mark.parametrize(
    ("relative", "old", "new", "control"),
    [
        (
            FILES[4],
            "https://docs.aws.amazon.com/bedrock",
            "http://docs.aws.amazon.com/bedrock",
            "official source URL",
        ),
        (
            FILES[4],
            "https://docs.aws.amazon.com/bedrock",
            "https://example.com/bedrock",
            "official source URL",
        ),
        (FILES[4], "NO-GO PARA INFERENCIA BEDROCK REAL", "GO", "documentation NO-GO"),
        (
            FILES[4],
            "not\nproduction-ready",
            "production-ready",
            "documentation not production-ready",
        ),
        (
            FILES[5],
            "bedrock-access-preflight.md",
            "missing.md",
            "access design preflight link",
        ),
        (
            FILES[6],
            "bedrock-access-preflight.md",
            "missing.md",
            "Copilot preflight link",
        ),
        (FILES[7], "WA-032", "WA-999", "WA-032 tracking"),
        (FILES[8], "WA-032", "WA-999", "WA-032 tracking"),
        (
            FILES[9],
            "- **Estado:** Proposed",
            "- **Estado:** Accepted",
            "ADR-013 remains Proposed",
        ),
    ],
)
def test_document_controls_fail(
    repository: Path, relative: str, old: str, new: str, control: str
):
    replace(repository, relative, old, new)
    rejected(repository, control)


def test_unterminated_fence_fails(repository: Path):
    target = path(repository, FILES[4])
    target.write_text(target.read_text() + "\n```text\n")
    rejected(repository, "unterminated fenced code block")


def test_root_cli_is_isolated(repository: Path):
    result = subprocess.run(
        [sys.executable, str(repository / FILES[-1]), "--root", str(repository)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "Bedrock access preflight controls passed.\n"


def test_crlf_copy_passes(repository: Path):
    for relative in (FILES[0], FILES[4]):
        target = path(repository, relative)
        target.write_bytes(target.read_text().replace("\n", "\r\n").encode())
    run_guardrail(repository)


def test_mutations_do_not_touch_checkout(repository: Path):
    original = (ROOT / FILES[1]).read_bytes()
    data = load(repository, FILES[1])
    data["enabled"] = True
    write(repository, FILES[1], data)
    rejected(repository, "preflight enabled")
    assert (ROOT / FILES[1]).read_bytes() == original


DYNAMIC_SHELL_CASES = (
    ('eval "true"', "dynamic shell execution is forbidden"),
    ('command eval "true"', "dynamic shell execution is forbidden"),
    ('builtin eval "true"', "dynamic shell execution is forbidden"),
    ('bash -c "true"', "dynamic shell execution is forbidden"),
    ('sh -c "true"', "dynamic shell execution is forbidden"),
    ("source script.sh", "dynamic shell execution is forbidden"),
    (". script.sh", "dynamic shell execution is forbidden"),
    ("alias awsx=aws", "dynamic AWS command is forbidden"),
    ('run_aws() { aws "$@"; }', "dynamic AWS command is forbidden"),
    ('$(printf true)', "dynamic shell execution is forbidden"),
    ('parts=(aws iam list-roles)', "dynamic AWS command is forbidden"),
    ('bash <<EOF', "dynamic shell execution is forbidden"),
)


@pytest.mark.parametrize(("fragment", "control"), DYNAMIC_SHELL_CASES)
def test_dynamic_shell_is_rejected(
    repository: Path, fragment: str, control: str
) -> None:
    anchor = "          set +e\n          aws sts get-caller-identity"
    replacement = f"          {fragment}\n{anchor}"
    replace(repository, FILES[0], anchor, replacement)
    rejected(repository, control)


DYNAMIC_AWS_CASES = (
    ('service=iam\n          aws "$service" list-roles',),
    ('operation=list-roles\n          aws iam "$operation"',),
    ('aws_cmd=aws\n          "$aws_cmd" iam list-roles',),
    ('service=sts\n          aws "$service" get-caller-identity',),
    ('operation=get-caller-identity\n          aws sts "$operation"',),
    ('aws "$(printf iam)" list-roles',),
    ('aws iam "$(printf list-roles)"',),
    ('parts=(aws iam list-roles)\n          "${parts[@]}"',),
    ('run_aws() { aws "$@"; }\n          run_aws iam list-roles',),
    ('alias awsx=aws\n          awsx iam list-roles',),
    ('name=aws_cmd\n          aws_cmd=aws\n          "${!name}" iam list-roles',),
    ('args="iam list-roles"\n          aws $args',),
    ('service=bedrock\n          aws "$service" list-foundation-models',),
    ('operation=list-foundation-models\n          aws bedrock "$operation"',),
)


@pytest.mark.parametrize("lines", DYNAMIC_AWS_CASES)
def test_dynamic_aws_commands_are_rejected(repository: Path, lines: tuple[str]) -> None:
    fragment = lines[0]
    anchor = "          set +e\n          aws sts get-caller-identity"
    replacement = f"          {fragment}\n{anchor}"
    replace(repository, FILES[0], anchor, replacement)
    rejected(repository, "dynamic AWS command is forbidden")


STDERR_MUTATIONS = (
    (' 2> "$raw_dir/identity.stderr"', "", "raw AWS stdout and stderr redirected"),
    (
        ' 2> "$raw_dir/identity.stderr"',
        " 2>&1",
        "raw AWS stdout and stderr redirected",
    ),
    (
        ' 2> "$raw_dir/identity.stderr"',
        " 2> /dev/stderr",
        "raw AWS stdout and stderr redirected",
    ),
    (
        ' 2> "$raw_dir/identity.stderr"',
        " 2> >(tee error.log)",
        "raw AWS stdout and stderr redirected",
    ),
    (
        ' 2> "$raw_dir/identity.stderr"',
        " 2> $GITHUB_OUTPUT",
        "no GitHub output evidence",
    ),
    (
        ' 2> "$raw_dir/identity.stderr"',
        " 2> $GITHUB_ENV",
        "no GitHub environment evidence",
    ),
    (
        ' 2> "$raw_dir/identity.stderr"',
        " 2> $GITHUB_STEP_SUMMARY",
        "no step summary evidence",
    ),
    (
        "path: bedrock-preflight-evidence.json",
        "path: ${{ runner.temp }}",
        "sanitized artifact only",
    ),
    (
        "          python3 scripts/sanitize_bedrock_preflight.py",
        '          cp "$raw_dir/identity.stderr" "$output"\n          python3 scripts/sanitize_bedrock_preflight.py',
        "exact raw error files",
    ),
    (
        'fail_aws "identity_check_failed"',
        "fail_aws",
        "fixed AWS error categories",
    ),
    (
        'fail_aws "identity_check_failed"',
        'fail_aws "$error"',
        "fixed AWS error categories",
    ),
    (
        'rm -rf "$work_dir"',
        'rm -rf "$raw_dir"',
        "raw temporary cleanup",
    ),
    ("trap cleanup EXIT", "trap true EXIT", "raw temporary cleanup trap"),
    (
        'test "$status" -eq 0 || fail_aws "identity_check_failed"',
        'test "$status" -eq 0 || cat "$raw_dir/identity.stderr"',
        "no raw error output",
    ),
    (
        'fail_aws() { printf \'%s\\n\' "$1" >&2; exit 1; }',
        'fail_aws() { cat "$raw_dir/identity.stderr"; exit 1; }',
        "(?:no raw error output|sanitized AWS error handler)",
    ),
)


@pytest.mark.parametrize(("old", "new", "control"), STDERR_MUTATIONS)
def test_stderr_controls_are_fail_closed(
    repository: Path, old: str, new: str, control: str
) -> None:
    replace(repository, FILES[0], old, new)
    rejected(repository, control)


STATIC_SHELL_MUTATIONS = (
    ("set -euo pipefail", "set -eu", "strict shell mode"),
    ("umask 077", "umask 022", "private temporary permissions"),
    (
        'mktemp -d "${RUNNER_TEMP}/bedrock-preflight.XXXXXX"',
        '"${RUNNER_TEMP}/bedrock-preflight"',
        "secure temporary directory",
    ),
    ("set +x", "set -x", "shell tracing disabled"),
    ("set +x", "printenv\n          set +x", "no environment dump"),
    ("set +x", "env\n          set +x", "no environment dump"),
    ("set +x", "tee error.log\n          set +x", "no raw tee"),
    ("set +x", "cat raw.stderr\n          set +x", "no raw error output"),
    ("--output json", "--debug --output json", "debug disabled"),
    (
        "--output json",
        "--endpoint-url https://example.com --output json",
        "AWS endpoint and TLS controls",
    ),
)


@pytest.mark.parametrize(("old", "new", "control"), STATIC_SHELL_MUTATIONS)
def test_static_shell_controls_are_enforced(
    repository: Path, old: str, new: str, control: str
) -> None:
    replace(repository, FILES[0], old, new)
    rejected(repository, control)


CATEGORY_MUTATIONS = tuple(
    (category, f"changed_{category}", "fixed AWS error categories")
    for category in (
        "identity_check_failed",
        "foundation_models_list_failed",
        "foundation_model_get_failed",
        "inference_profiles_list_failed",
        "inference_profile_get_failed",
    )
)


def test_error_handler_is_fixed(repository: Path) -> None:
    replace(
        repository,
        FILES[0],
        'fail_aws() { printf \'%s\\n\' "$1" >&2; exit 1; }',
        'fail_aws() { printf "$1" >&2; exit 1; }',
    )
    rejected(repository, "sanitized AWS error handler")


@pytest.mark.parametrize(("old", "new", "control"), CATEGORY_MUTATIONS)
def test_error_categories_and_handler_are_fixed(
    repository: Path, old: str, new: str, control: str
) -> None:
    replace(repository, FILES[0], old, new)
    rejected(repository, control)


SECURE_PATH_MUTATIONS = (
    ('raw_dir="${work_dir}/raw"', 'raw_dir="${GITHUB_WORKSPACE}/raw"'),
    ('raw_dir="${work_dir}/raw"', 'raw_dir="./raw"'),
    ('raw_dir="${work_dir}/raw"', 'raw_dir="/tmp/raw"'),
    ('raw_dir="${work_dir}/raw"', 'raw_dir="/var/tmp/raw"'),
    ('raw_dir="${work_dir}/raw"', 'raw_dir="${HOME}/raw"'),
    ('raw_dir="${work_dir}/raw"', 'raw_dir="${PWD}/raw"'),
    ('raw_dir="${work_dir}/raw"', 'raw_dir="${work_dir}/../raw"'),
    (
        'candidate="${work_dir}/candidate.json"',
        'candidate="${GITHUB_WORKSPACE}/candidate.json"',
    ),
    ('candidate="${work_dir}/candidate.json"', 'candidate="candidate.json"'),
    ('candidate="${work_dir}/candidate.json"', 'candidate="../candidate.json"'),
    (
        '"$raw_dir/identity.json"',
        '"${GITHUB_WORKSPACE}/identity.json"',
    ),
    (
        '"$raw_dir/identity.stderr"',
        '"${GITHUB_WORKSPACE}/identity.stderr"',
    ),
    (
        'candidate="${work_dir}/candidate.json"',
        'candidate="${RUNNER_TEMP}/candidate.json"',
    ),
    (
        'raw_dir="${work_dir}/raw"',
        'raw_dir="${work_dir}/raw"\n          raw_dir="/tmp/raw"',
    ),
    (
        'candidate="${work_dir}/candidate.json"',
        'candidate="${work_dir}/candidate.json"\n          candidate="/tmp/candidate.json"',
    ),
    (
        'mkdir -p "$raw_dir"',
        'mkdir -p "$raw_dir"\n          ln -s "${GITHUB_WORKSPACE}" "${work_dir}/raw-link"',
    ),
    (
        'mkdir -p "$raw_dir"',
        'mkdir -p "$raw_dir"\n          ln -s "${GITHUB_WORKSPACE}/candidate.json" "$candidate"',
    ),
    ('cleanup() { rm -rf "$work_dir"; }', 'cleanup() { rm -rf "$raw_dir"; }'),
    ('cleanup() { rm -rf "$work_dir"; }', 'cleanup() { rm -f "$candidate"; }'),
    ('cleanup() { rm -rf "$work_dir"; }', 'cleanup() { rm -rf "/tmp/other"; }'),
    (
        'work_dir="$(mktemp -d "${RUNNER_TEMP}/bedrock-preflight.XXXXXX")"',
        'work_dir="$(mktemp "${RUNNER_TEMP}/bedrock-preflight.XXXXXX")"',
    ),
    (
        'work_dir="$(mktemp -d "${RUNNER_TEMP}/bedrock-preflight.XXXXXX")"',
        'work_dir="${RUNNER_TEMP}/bedrock-preflight"',
    ),
    (
        'work_dir="$(mktemp -d "${RUNNER_TEMP}/bedrock-preflight.XXXXXX")"',
        'work_dir="/tmp/bedrock-preflight"',
    ),
    ("trap cleanup EXIT", "trap cleanup INT TERM"),
)


@pytest.mark.parametrize(("old", "new"), SECURE_PATH_MUTATIONS)
def test_all_raw_paths_remain_in_secure_tree(
    repository: Path, old: str, new: str
) -> None:
    replace(repository, FILES[0], old, new)
    rejected(
        repository,
        "(?:raw files must remain under the secure temporary directory|secure temporary directory|raw temporary cleanup|raw temporary cleanup trap|raw AWS stdout and stderr redirected)",
    )


AWS_ARGUMENT_MUTATIONS = (
    ("--no-cli-pager --output json", "--profile attacker --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--endpoint-url https://example.com --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--debug --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--no-verify-ssl --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--ca-bundle example.pem --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--cli-connect-timeout 1 --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--cli-read-timeout 1 --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--color on --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--query Account --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--unknown value --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "extra --no-cli-pager --output json"),
    ("--no-cli-pager --output json", "--output json"),
    ("--no-cli-pager --output json", "--no-cli-pager"),
    ("--no-cli-pager --output json", "--no-cli-pager --output text"),
    ("--no-cli-pager --output json", "--no-cli-pager --output yaml"),
    ("--no-cli-pager --output json", "--no-cli-pager --no-cli-pager --output json"),
    ("--region eu-west-1 --no-cli-pager", "--region us-east-1 --no-cli-pager"),
    ("--region eu-west-1 --no-cli-pager", "--region eu-west-1 --region eu-west-1 --no-cli-pager"),
    ("--region eu-west-1 --no-cli-pager", "--region $SOURCE_REGION --no-cli-pager"),
    ("--region eu-west-1 --no-cli-pager", "$REGION_FLAG eu-west-1 --no-cli-pager"),
    (
        "--model-identifier amazon.nova-lite-v1:0",
        "--model-identifier amazon.nova-pro-v1:0",
    ),
    (
        "--model-identifier amazon.nova-lite-v1:0",
        "--model-identifier $MODEL_ID",
    ),
    (
        "--inference-profile-identifier eu.amazon.nova-lite-v1:0",
        "--inference-profile-identifier us.amazon.nova-lite-v1:0",
    ),
    (
        "--inference-profile-identifier eu.amazon.nova-lite-v1:0",
        "--inference-profile-identifier $INFERENCE_PROFILE_ID",
    ),
    ("--region eu-west-1 --no-cli-pager", "--no-cli-pager --region eu-west-1"),
)


@pytest.mark.parametrize(("old", "new"), AWS_ARGUMENT_MUTATIONS)
def test_aws_argument_sequences_are_exact(
    repository: Path, old: str, new: str
) -> None:
    replace(repository, FILES[0], old, new)
    rejected(
        repository,
        "(?:AWS command arguments are not allowed|AWS endpoint and TLS controls|debug disabled)",
    )


AWS_ENVIRONMENT_MUTATIONS = (
    "AWS_PROFILE=attacker",
    "AWS_DEFAULT_PROFILE=attacker",
    "AWS_SHARED_CREDENTIALS_FILE=/tmp/credentials",
    "AWS_CONFIG_FILE=/tmp/config",
    "AWS_ACCESS_KEY_ID=example",
    "AWS_SECRET_ACCESS_KEY=example",
    "AWS_SESSION_TOKEN=example",
    "AWS_ROLE_ARN=example",
    "AWS_WEB_IDENTITY_TOKEN_FILE=/tmp/token",
    "credential_process=example",
    "source_profile=example",
)


@pytest.mark.parametrize("declaration", AWS_ENVIRONMENT_MUTATIONS)
def test_manual_aws_credential_environment_is_rejected(
    repository: Path, declaration: str
) -> None:
    anchor = "          set +e\n          aws sts get-caller-identity"
    replace(repository, FILES[0], anchor, f"          {declaration}\n{anchor}")
    rejected(repository, "manual AWS credential configuration is forbidden")
