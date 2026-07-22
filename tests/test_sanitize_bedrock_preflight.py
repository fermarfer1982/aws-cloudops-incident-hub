from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.sanitize_bedrock_preflight import sanitize

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sanitize_bedrock_preflight.py"


@pytest.fixture
def evidence() -> dict:
    names = [
        "catalog_model_present",
        "foundation_model_details_present",
        "identity_present",
        "inference_executed",
        "inference_profile_present",
        "oidc_authentication_succeeded",
        "read_permissions_compatible",
        "source_region_exact",
    ]
    return {
        "schema_version": "bedrock-access-preflight/v1",
        "generated_at": "2026-07-22T09:06:50Z",
        "commit_sha": "a" * 40,
        "source_region": "eu-west-1",
        "model_id": "amazon.nova-lite-v1:0",
        "inference_profile_id": "eu.amazon.nova-lite-v1:0",
        "checks": [
            {
                "name": name,
                "status": "NOT_CHECKED" if name == "inference_executed" else "PASS",
            }
            for name in names
        ],
        "official_sources": [
            "https://docs.aws.amazon.com/bedrock/latest/userguide/models-get-info.html",
            "https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-view.html",
            "https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html",
            "https://docs.github.com/en/actions/reference/security/oidc",
        ],
        "tool_version": "1.0.0",
    }


def rejected(document: object, control: str) -> None:
    with pytest.raises(SystemExit, match=control):
        sanitize(document)


def test_valid_evidence_passes(evidence: dict):
    assert sanitize(evidence) == evidence


@pytest.mark.parametrize(
    "value",
    [
        "123456" + "789012",
        "account=123456" + "789012",
        "arn:aws:iam::" + "0" * 12 + ":role/example",
        "arn:aws-us-gov:sts::" + "0" * 12 + ":assumed-role/x/y",
        "arn:aws-cn:bedrock:cn-north-1::foundation-model/example",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "ASIA" + "ABCDEFGHIJKLMNOP",
        "token=example",
        "secret: example",
        "password=example",
        "client_secret=example",
        "https://example.com/?X-Amz-Signature=abc",
        "https://example.com/?AWSAccessKeyId=abc",
        "request_id=abc",
        "x-amzn-requestid: abc",
        "550e8400-e29b-41d4-a716-446655440000",
        "operator@example.com",
        "10.0.0.1",
        "127.0.0.1",
        "192.168.1.1",
        "172.16.0.1",
        "172.31.255.255",
    ],
)
def test_sensitive_values_are_rejected(evidence: dict, value: str):
    evidence["checks"][0]["status"] = value
    rejected(evidence, "(?:check status|sensitive value)")


@pytest.mark.parametrize(
    ("key", "value", "control"),
    [
        ("schema_version", "v2", "schema version"),
        ("tool_version", "2.0.0", "tool version"),
        ("source_region", "us-east-1", "source region"),
        ("model_id", "amazon.nova-pro-v1:0", "model ID"),
        ("inference_profile_id", "us.amazon.nova-lite-v1:0", "inference profile ID"),
        ("generated_at", "2026-07-22", "UTC timestamp"),
        ("generated_at", "2026-07-22T09:06:50+00:00", "UTC timestamp"),
        ("commit_sha", "abc", "commit SHA"),
        ("commit_sha", "A" * 40, "commit SHA"),
        ("checks", {}, "exact checks"),
        ("checks", [], "exact checks"),
        ("official_sources", [], "official sources"),
        ("official_sources", "https://docs.aws.amazon.com/x", "official sources"),
    ],
)
def test_invalid_top_level_values_fail(
    evidence: dict, key: str, value: object, control: str
):
    evidence[key] = value
    rejected(evidence, control)


@pytest.mark.parametrize("mutation", ["extra", "missing", "not_object"])
def test_top_level_shape_is_exact(evidence: dict, mutation: str):
    if mutation == "extra":
        evidence["account_id"] = "redacted"
        rejected(evidence, "exact evidence keys")
    elif mutation == "missing":
        evidence.pop("tool_version")
        rejected(evidence, "exact evidence keys")
    else:
        rejected([], "input must be a JSON object")


@pytest.mark.parametrize(
    ("mutation", "control"),
    [
        ("extra_key", "exact check keys"),
        ("missing_key", "exact check keys"),
        ("not_object", "exact check keys"),
        ("unknown_name", "check name"),
        ("duplicate", "duplicate check"),
        ("invalid_status", "check status"),
        ("numeric_status", "check status"),
    ],
)
def test_check_shape_is_exact(evidence: dict, mutation: str, control: str):
    if mutation == "extra_key":
        evidence["checks"][0]["detail"] = "none"
    elif mutation == "missing_key":
        evidence["checks"][0].pop("status")
    elif mutation == "not_object":
        evidence["checks"][0] = "PASS"
    elif mutation == "unknown_name":
        evidence["checks"][0]["name"] = "unknown"
    elif mutation == "duplicate":
        evidence["checks"][1]["name"] = evidence["checks"][0]["name"]
    elif mutation == "invalid_status":
        evidence["checks"][0]["status"] = "SUCCESS"
    else:
        evidence["checks"][0]["status"] = 1
    rejected(evidence, control)


def test_inference_cannot_be_reported_as_executed(evidence: dict):
    next(
        check for check in evidence["checks"] if check["name"] == "inference_executed"
    )["status"] = "PASS"
    rejected(evidence, "inference must remain unexecuted")


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.aws.amazon.com/x",
        "https://example.com/x",
        "https://docs.aws.amazon.com.evil.example/x",
        "https://user@docs.aws.amazon.com/x",
        "https://user:password@docs.aws.amazon.com/x",
        "https://docs.aws.amazon.com:443/x",
        "https://docs.aws.amazon.com",
        123,
    ],
)
def test_unofficial_sources_fail(evidence: dict, url: object):
    evidence["official_sources"][0] = url
    rejected(evidence, "official sources")


def test_cli_output_is_deterministic_and_input_is_unchanged(
    tmp_path: Path, evidence: dict
):
    source = tmp_path / "input.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    source.write_text(json.dumps(evidence), encoding="utf-8")
    original = source.read_bytes()
    for output in (first, second):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(source),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""
    assert source.read_bytes() == original
    assert first.read_bytes() == second.read_bytes()


def test_cli_rejects_input_overwrite(tmp_path: Path, evidence: dict):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(evidence), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert (
        result.stderr
        == "Bedrock preflight sanitizer failed: input and output must differ\n"
    )


@pytest.mark.parametrize("content", ["{", "[]", '"text"', "null"])
def test_cli_rejects_invalid_json_documents(tmp_path: Path, content: str):
    source = tmp_path / "input.json"
    output = tmp_path / "output.json"
    source.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_mutations_do_not_share_state(evidence: dict):
    mutated = copy.deepcopy(evidence)
    mutated["source_region"] = "us-east-1"
    rejected(mutated, "source region")
    assert sanitize(evidence) == evidence
