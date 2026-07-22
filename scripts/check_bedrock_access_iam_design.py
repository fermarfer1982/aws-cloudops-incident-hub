#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path("config/bedrock-access-readiness.json")
POLICY = Path("policies/bedrock-nova-lite-eu-invoke.template.json")
DESIGN = Path("docs/bedrock-access-and-iam-design.md")
COPILOT = Path("docs/bedrock-incident-copilot.md")
BACKLOG = Path("docs/well-architected-backlog.md")
REVIEW = Path("docs/well-architected-review.md")
ADR = Path("docs/adr/013-amazon-bedrock-incident-copilot.md")

REGIONS = ["eu-central-1", "eu-north-1", "eu-west-1", "eu-west-3"]
PROFILE_ARN = (
    "arn:${AWS_PARTITION}:bedrock:${SOURCE_REGION}:${AWS_ACCOUNT_ID}:"
    "inference-profile/eu.amazon.nova-lite-v1:0"
)
MODEL_ARNS = [
    f"arn:${{AWS_PARTITION}}:bedrock:{region}::foundation-model/"
    "amazon.nova-lite-v1:0"
    for region in REGIONS
]
CONFIG_KEYS = {
    "account_access_checked",
    "account_access_verified",
    "api",
    "blockers",
    "destination_regions_snapshot",
    "destination_regions_verified_for_execution",
    "enabled",
    "human_execution_approval",
    "iam_policy_applied",
    "inference_authorized",
    "inference_profile_id",
    "model_id",
    "policy_version",
    "required_invoke_action",
    "review_required_before_execution",
    "scp_compatibility_checked",
    "source_region",
    "sources",
    "status",
    "streaming_action_allowed",
    "terms_reviewed",
}
FALSE_GATES = {
    "account_access_checked",
    "account_access_verified",
    "destination_regions_verified_for_execution",
    "enabled",
    "human_execution_approval",
    "iam_policy_applied",
    "inference_authorized",
    "scp_compatibility_checked",
    "streaming_action_allowed",
    "terms_reviewed",
}
SOURCE_KEYS = {"interpretation", "uncertainty", "url", "verified_at"}
OFFICIAL_HOSTS = {"docs.aws.amazon.com", "aws.amazon.com"}


def fail(control: str) -> None:
    raise SystemExit(f"Bedrock access/IAM design control failed: {control}")


def require(value: bool, control: str) -> None:
    if not value:
        fail(control)


def read(root: Path, relative: Path) -> str:
    path = root / relative
    require(path.is_file(), f"missing {relative}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail(f"unreadable {relative}")


def load_json(root: Path, relative: Path) -> dict[str, object]:
    try:
        value = json.loads(read(root, relative))
    except json.JSONDecodeError:
        fail(f"valid JSON: {relative}")
    require(type(value) is dict, f"JSON object: {relative}")
    return value


def exact(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


def timestamp(value: object) -> bool:
    if type(value) is not str or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def official_url(value: object) -> bool:
    if type(value) is not str or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in OFFICIAL_HOSTS
        and parsed.username is None
        and parsed.password is None
        and port is None
        and bool(parsed.path)
    )


def strip_fences(document: str) -> str:
    output: list[str] = []
    active: tuple[str, int] | None = None
    opening = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\r\n]*(?:\r\n|\r|\n)?$")
    for line in document.splitlines(keepends=True):
        ending_match = re.search(r"(?:\r\n|\r|\n)$", line)
        ending = ending_match.group(0) if ending_match else ""
        if active is None:
            match = opening.fullmatch(line)
            if match:
                marker = match.group(1)
                active = (marker[0], len(marker))
                output.append(ending)
            else:
                output.append(line)
            continue
        closing = re.compile(
            rf"^ {{0,3}}{re.escape(active[0])}{{{active[1]},}}[ \t]*(?:\r\n|\r|\n)?$"
        )
        if closing.fullmatch(line):
            active = None
        output.append(ending)
    require(active is None, "unterminated fenced code block")
    return "".join(output)


def validate_config(data: dict[str, object]) -> None:
    require(set(data) == CONFIG_KEYS, "exact configuration keys")
    expected = {
        "api": "Converse",
        "destination_regions_snapshot": REGIONS,
        "inference_profile_id": "eu.amazon.nova-lite-v1:0",
        "model_id": "amazon.nova-lite-v1:0",
        "policy_version": "bedrock-access-readiness/v1",
        "required_invoke_action": "bedrock:InvokeModel",
        "review_required_before_execution": True,
        "source_region": "eu-west-1",
        "status": "proposed-disabled",
    }
    for key, value in expected.items():
        require(exact(data[key], value), f"configuration {key}")
    for key in FALSE_GATES:
        require(exact(data[key], False), f"configuration {key}")
    blockers = data["blockers"]
    require(type(blockers) is list and len(blockers) == 6, "exact blockers")
    require(
        all(type(item) is str and item.strip() for item in blockers), "blocker strings"
    )
    sources = data["sources"]
    require(type(sources) is list and len(sources) >= 5, "official AWS sources")
    for source in sources:
        require(type(source) is dict and set(source) == SOURCE_KEYS, "exact source keys")
        require(official_url(source["url"]), "official AWS sources")
        require(timestamp(source["verified_at"]), "source UTC timestamp")
        require(
            type(source["interpretation"]) is str
            and bool(source["interpretation"].strip()),
            "source interpretation",
        )
        require(
            type(source["uncertainty"]) is str and bool(source["uncertainty"].strip()),
            "source uncertainty",
        )


def validate_policy(data: dict[str, object]) -> None:
    require(set(data) == {"metadata", "policy_template"}, "inert policy envelope")
    require(
        data["metadata"]
        == {
            "directive": "DO_NOT_APPLY",
            "human_review_required": True,
            "status": "disabled",
        },
        "inert policy metadata",
    )
    expected = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": "bedrock:InvokeModel",
                "Effect": "Allow",
                "Resource": PROFILE_ARN,
                "Sid": "InvokeApprovedEuInferenceProfile",
            },
            {
                "Action": "bedrock:InvokeModel",
                "Condition": {
                    "StringEquals": {"bedrock:InferenceProfileArn": PROFILE_ARN}
                },
                "Effect": "Allow",
                "Resource": MODEL_ARNS,
                "Sid": "InvokeNovaLiteOnlyThroughApprovedProfile",
            },
        ],
    }
    require(data["policy_template"] == expected, "exact least-privilege policy")
    rendered = json.dumps(data, sort_keys=True)
    require("*" not in rendered, "no wildcards")
    require(
        all(token in rendered for token in ("${AWS_PARTITION}", "${SOURCE_REGION}", "${AWS_ACCOUNT_ID}")),
        "mandatory placeholders",
    )
    require(not re.search(r"(?<!\$\{)\b\d{12}\b", rendered), "no real account ID")
    require("Principal" not in rendered and "role/" not in rendered, "no principal or role ARN")


def validate_documents(root: Path) -> None:
    documents = {
        relative: strip_fences(read(root, relative))
        for relative in (DESIGN, COPILOT, BACKLOG, REVIEW, ADR)
    }
    design = documents[DESIGN]
    require("NO-GO PARA INFERENCIA BEDROCK REAL" in design, "documentation NO-GO")
    require("not production-ready" in design, "documentation not production-ready")
    require("ADR-013 remains **Proposed**" in design, "documentation ADR-013 Proposed")
    require(
        "bedrock-access-and-iam-design.md" in documents[COPILOT],
        "Copilot design link",
    )
    require("WA-031" in documents[BACKLOG], "backlog design control")
    require("WA-031" in documents[REVIEW], "review design control")
    require("- **Estado:** Proposed" in documents[ADR], "ADR-013 remains Proposed")
    combined = "\n".join(documents.values())
    forbidden = (
        r"^ADR-013 (?:is |está |esta )?Accepted\.?$",
        r"^The project (?:is|está|esta|queda) production-ready\.?$",
        r"^Inference (?:is |queda )?authorized\.?$",
        r"^La inferencia (?:está|esta|queda) autorizada\.?$",
        r"^IAM (?:is |está |esta |queda )?(?:applied|aplicad[oa])\.?$",
        r"^Account access (?:is |has been )?(?:verified|checked)\.?$",
        r"^El acceso de (?:la )?cuenta (?:está|esta|queda) verificado\.?$",
        r"^SCP (?:was|has been|fue|ha sido) modified\.?$",
        r"^AmazonBedrockFullAccess (?:is required|required|se concede|se aplica)\.?$",
    )
    for pattern in forbidden:
        require(
            not re.search(pattern, combined, re.IGNORECASE | re.MULTILINE),
            "documentation contradiction",
        )


def run_guardrail(root: Path) -> None:
    root = root.resolve()
    validate_config(load_json(root, CONFIG))
    validate_policy(load_json(root, POLICY))
    validate_documents(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    run_guardrail(args.root)
    print("Bedrock access/IAM design controls passed.")


if __name__ == "__main__":
    main()
