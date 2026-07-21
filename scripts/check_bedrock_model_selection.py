#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path("config/bedrock-model-selection.json")
DOC = Path("docs/bedrock-model-selection.md")
ADR = Path("docs/adr/013-amazon-bedrock-incident-copilot.md")
REVIEW = Path("docs/well-architected-review.md")
EXACT_KEYS = {
    "api",
    "availability_verified_at",
    "cross_region_scope",
    "destination_regions_snapshot",
    "enabled",
    "endpoint",
    "fallback_model",
    "fallback_region",
    "geo_inference_profile_id",
    "iam_authorized",
    "input_modality",
    "model_access_verified_in_account",
    "model_name",
    "output_modality",
    "parameters",
    "policy_version",
    "pricing_snapshot",
    "pricing_verified_at",
    "provider",
    "regional_model_id",
    "review_required_before_execution",
    "source_region",
    "sources",
    "status",
    "streaming",
}
PARAMETERS = {
    "application_inference_profile": False,
    "automatic_retries": 0,
    "caching": False,
    "documents": False,
    "guardrails": False,
    "images": False,
    "max_requests": 1,
    "max_tokens": 300,
    "temperature": 0,
    "timeout_seconds": None,
    "tools": False,
    "top_p": 1,
    "video": False,
}


def fail(control: str) -> None:
    raise SystemExit(f"Bedrock model selection control failed: {control}")


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


def utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def run_guardrail(root: Path) -> None:
    raw = read(root, CONFIG)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        fail("valid JSON")
    require(isinstance(data, dict), "JSON object")
    require(set(data) == EXACT_KEYS, "exact configuration keys")
    expected = {
        "status": "proposed-disabled",
        "provider": "amazon",
        "model_name": "Amazon Nova Lite",
        "regional_model_id": "amazon.nova-lite-v1:0",
        "geo_inference_profile_id": "eu.amazon.nova-lite-v1:0",
        "source_region": "eu-west-1",
        "endpoint": "bedrock-runtime",
        "api": "Converse",
        "streaming": False,
        "input_modality": "text",
        "output_modality": "text",
        "cross_region_scope": "EU",
        "enabled": False,
        "iam_authorized": False,
        "model_access_verified_in_account": False,
        "fallback_model": None,
        "fallback_region": None,
        "review_required_before_execution": True,
        "policy_version": "bedrock-model-selection/v1",
        "destination_regions_snapshot": [
            "eu-central-1",
            "eu-north-1",
            "eu-west-1",
            "eu-west-3",
        ],
    }
    for key, value in expected.items():
        require(data[key] == value, key)
    require(data["parameters"] == PARAMETERS, "exact inert parameters")
    for key in ("pricing_verified_at", "availability_verified_at"):
        require(utc_timestamp(data[key]), key)
    sources = data["sources"]
    require(isinstance(sources, list) and len(sources) >= 7, "official sources")
    require(
        all(
            isinstance(item, str)
            and urlparse(item).scheme == "https"
            and (urlparse(item).hostname or "").endswith(
                ("aws.amazon.com", "amazonaws.com")
            )
            for item in sources
        ),
        "official AWS sources",
    )
    pricing = data["pricing_snapshot"]
    require(isinstance(pricing, dict), "pricing snapshot")
    require(
        pricing.get("estimated_call_cost") == 0.000132
        and pricing.get("hard_ceiling") == 0.0002,
        "documentary budget",
    )
    doc, adr, review = read(root, DOC), read(root, ADR), read(root, REVIEW)
    for phrase in (
        "NO-GO PARA INFERENCIA BEDROCK REAL",
        "proposed-disabled",
        "no hay autorización IAM",
        "no se ha verificado acceso",
        "Los perfiles `global.*`, `us.*` y `apac.*` están prohibidos",
        "sin fallback",
        "not production-ready",
    ):
        require(phrase in doc, f"documentation: {phrase}")
    require("- **Estado:** Proposed" in adr, "ADR-013 remains Proposed")
    require("Not production-ready" in review, "project not production-ready")
    combined = raw + "\n" + doc
    require(not re.search(r"arn:[a]ws", combined, re.I), "no ARN")
    require(not re.search(r"\b\d{12}\b", combined), "no account ID")
    require("bedrock:InvokeModel" not in combined, "no Bedrock permission")
    require("AUTORIZADA PARA INFERENCIA" not in doc, "no inference authorization")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    run_guardrail(args.root.resolve())
    print("Bedrock model selection controls passed.")


if __name__ == "__main__":
    main()
