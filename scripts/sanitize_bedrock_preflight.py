#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

TOP_LEVEL_KEYS = {
    "checks",
    "commit_sha",
    "generated_at",
    "inference_profile_id",
    "model_id",
    "official_sources",
    "schema_version",
    "source_region",
    "tool_version",
}
CHECK_KEYS = {"name", "status"}
CHECK_NAMES = {
    "catalog_model_present",
    "foundation_model_details_present",
    "identity_present",
    "inference_executed",
    "inference_profile_present",
    "oidc_authentication_succeeded",
    "read_permissions_compatible",
    "source_region_exact",
}
CHECK_STATUSES = {"PASS", "FAIL", "NOT_CHECKED"}
OFFICIAL_HOSTS = {"docs.aws.amazon.com", "aws.amazon.com", "docs.github.com"}
SENSITIVE_PATTERNS = (
    re.compile(r"\barn:(?:aws|aws-us-gov|aws-cn):", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])\d{12}(?![A-Za-z0-9])"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(
        r"(?:x-amz-(?:credential|signature|security-token)|awsaccesskeyid)=",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:token|secret|password|client[_ -]?secret)\b\s*[:=]", re.IGNORECASE
    ),
    re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<![\w.])(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\w.])"),
    re.compile(r"(?<![\w.])192\.168\.\d{1,3}\.\d{1,3}(?![\w.])"),
    re.compile(r"(?<![\w.])172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}(?![\w.])"),
    re.compile(r"\b(?:request[_ -]?id|x-amzn-requestid)\b", re.IGNORECASE),
)


def fail(control: str) -> None:
    raise SystemExit(f"Bedrock preflight sanitizer failed: {control}")


def require(condition: bool, control: str) -> None:
    if not condition:
        fail(control)


def official_url(value: object) -> bool:
    if type(value) is not str:
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


def sanitize(document: object) -> dict[str, object]:
    require(type(document) is dict, "input must be a JSON object")
    require(set(document) == TOP_LEVEL_KEYS, "exact evidence keys")
    require(
        document["schema_version"] == "bedrock-access-preflight/v1", "schema version"
    )
    require(document["tool_version"] == "1.0.0", "tool version")
    require(document["source_region"] == "eu-west-1", "source region")
    require(document["model_id"] == "amazon.nova-lite-v1:0", "model ID")
    require(
        document["inference_profile_id"] == "eu.amazon.nova-lite-v1:0",
        "inference profile ID",
    )
    require(
        type(document["generated_at"]) is str
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", document["generated_at"]
        )
        is not None,
        "UTC timestamp",
    )
    require(
        type(document["commit_sha"]) is str
        and re.fullmatch(r"[0-9a-f]{40}", document["commit_sha"]) is not None,
        "commit SHA",
    )
    checks = document["checks"]
    require(type(checks) is list and len(checks) == len(CHECK_NAMES), "exact checks")
    names: set[str] = set()
    for check in checks:
        require(type(check) is dict and set(check) == CHECK_KEYS, "exact check keys")
        require(
            type(check["name"]) is str and check["name"] in CHECK_NAMES, "check name"
        )
        require(check["name"] not in names, "duplicate check")
        require(
            type(check["status"]) is str and check["status"] in CHECK_STATUSES,
            "check status",
        )
        names.add(check["name"])
    require(names == CHECK_NAMES, "exact checks")
    inference_check = next(
        check for check in checks if check["name"] == "inference_executed"
    )
    require(
        inference_check["status"] == "NOT_CHECKED", "inference must remain unexecuted"
    )
    sources = document["official_sources"]
    require(type(sources) is list and len(sources) >= 4, "official sources")
    require(all(official_url(source) for source in sources), "official sources")
    serialized = json.dumps(document, sort_keys=True, separators=(",", ":"))
    for pattern in SENSITIVE_PATTERNS:
        require(pattern.search(serialized) is None, "sensitive value")
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(
        args.input.resolve() != args.output.resolve(), "input and output must differ"
    )
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("valid JSON input")
    sanitized = sanitize(document)
    try:
        args.output.write_text(
            json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        fail("write output")


if __name__ == "__main__":
    main()
