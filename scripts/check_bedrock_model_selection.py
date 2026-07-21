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
PRICING = {
    "currency": "USD",
    "estimated_call_cost": 0.0001518,
    "estimated_input_cost": 0.000069,
    "estimated_output_cost": 0.0000828,
    "hard_ceiling": 0.0002,
    "input_price_per_million_tokens": 0.069,
    "input_price_per_thousand_tokens": 0.000069,
    "max_input_tokens": 1000,
    "max_output_tokens": 300,
    "output_price_per_million_tokens": 0.276,
    "output_price_per_thousand_tokens": 0.000276,
    "pricing_source": "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
    "AmazonBedrock/20260720215247/eu-west-1/index.json",
    "pricing_unit": "USD per 1K and 1M tokens",
    "pricing_verified_at": "2026-07-21T11:29:41Z",
    "service_tier": "standard",
    "snapshot_only": True,
}
OFFICIAL_HOSTS = {
    "aws.amazon.com",
    "docs.aws.amazon.com",
    "pricing.us-east-1.amazonaws.com",
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
    if type(value) is not str or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def exact_value(actual: object, expected: object) -> bool:
    """Compare JSON values without treating bool as a number."""
    return type(actual) is type(expected) and actual == expected


def exact_mapping(actual: object, expected: dict[str, object]) -> bool:
    return (
        type(actual) is dict
        and set(actual) == set(expected)
        and all(exact_value(actual[key], value) for key, value in expected.items())
    )


def official_url(value: object) -> bool:
    if type(value) is not str or any(ord(character) < 32 for character in value):
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


def strip_fenced_code_blocks(document: str) -> str:
    sanitized: list[str] = []
    marker: tuple[str, int] | None = None
    opening = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\r\n]*(?:\r\n|\r|\n)?$")
    for line in document.splitlines(keepends=True):
        ending_match = re.search(r"(?:\r\n|\r|\n)$", line)
        ending = ending_match.group(0) if ending_match else ""
        if marker is None:
            match = opening.fullmatch(line)
            if match:
                fence = match.group(1)
                marker = (fence[0], len(fence))
                sanitized.append(ending)
            else:
                sanitized.append(line)
            continue
        closing = re.compile(
            rf"^ {{0,3}}{re.escape(marker[0])}{{{marker[1]},}}[ \t]*(?:\r\n|\r|\n)?$"
        )
        if closing.fullmatch(line):
            marker = None
        sanitized.append(ending)
    require(marker is None, "unterminated fenced code block")
    return "".join(sanitized)


def validate_normative_document(document: str) -> None:
    normative = strip_fenced_code_blocks(document)
    validate_profile_authorizations(normative)
    clauses = [
        re.sub(r"[`*_]", "", clause).strip().lower()
        for clause in re.split(r"(?:\r?\n|;|\.(?:\s+|$))", normative)
        if clause.strip()
    ]
    forbidden = (
        r"\bla cuenta tiene garantizadas? \d+ solicitudes",
        r"\bla cuota de la cuenta (?:está|esta) verificada\b",
        r"\bla capacidad disponible (?:está|esta) garantizada\b",
        r"\btodos los datos permanecen en irlanda\b",
        r"\blos datos nunca salen de eu-west-1\b",
        r"\bel procesamiento ocurre exclusivamente en irlanda\b",
        r"\bla inferencia es estrictamente in-region\b",
        r"\bla inferencia (?:está|esta|queda) autorizada\b",
        r"\biam (?:está|esta|queda) autorizado\b",
        r"\bel acceso de (?:la )?cuenta (?:está|esta|queda) verificado\b",
        r"\bproducci[oó]n (?:está|esta|queda) aprobada\b",
        r"\badr-013 (?:está|esta|queda) accepted\b",
        r"\bel modelo (?:está|esta|queda) habilitado\b",
        r"\bla ejecuci[oó]n (?:está|esta|queda) permitida\b",
        r"\b(?:retry|reintento) autom[aá]tico (?:está|esta|queda) habilitado\b",
        r"\bfallback (?:está|esta|queda) permitido\b",
    )
    for clause in clauses:
        require(
            not any(re.search(pattern, clause) for pattern in forbidden),
            "documentation contradiction",
        )


def validate_profile_authorizations(document: str) -> None:
    profile_patterns = {
        "GLOBAL": r"\b(?:perfil(?:es)?\s+global(?:es)?|inferencia\s+global|"
        r"ámbito\s+global|scope\s+global|global\.|global)\b",
        "US": r"\b(?:perfil(?:es)?\s+us|perfil(?:es)?\s+estadounidense(?:s)?|"
        r"estados\s+unidos|ámbito\s+us|scope\s+us|us\.|us)\b",
        "APAC": r"\b(?:perfil(?:es)?\s+apac|perfil(?:es)?\s+asia[- ]pacífico|"
        r"inferencia\s+en\s+apac|ámbito\s+apac|scope\s+apac|apac\.|apac)\b",
    }
    authorization = re.compile(
        r"\b(?:está|esta|están|estan|queda|quedan)?\s*"
        r"(?:permitid[oa]s?|autorizad[oa]s?|aprobad[oa]s?)\b|"
        r"\bse\s+permite\b|\b(?:puede|podrá|podra)\s+"
        r"(?:usarse|utilizarse)\b",
        re.IGNORECASE,
    )
    negation = re.compile(
        r"\bno\s+(?:está|esta|están|estan|se\s+permite|puede|podrá|podra)\b|"
        r"\b(?:prohibid[oa]s?|bloquead[oa]s?)\b",
        re.IGNORECASE,
    )
    separators = re.compile(
        r"(?:;|\.(?:\s+|$)|\b(?:pero|sin\s+embargo|no\s+obstante|aunque)\b)",
        re.IGNORECASE,
    )
    for line in document.splitlines():
        inherited_profiles: set[str] = set()
        for clause in separators.split(re.sub(r"[`*_]", "", line)):
            profiles = {
                name
                for name, pattern in profile_patterns.items()
                if re.search(pattern, clause, re.IGNORECASE)
            }
            if profiles:
                inherited_profiles = profiles
            applicable = profiles or inherited_profiles
            if applicable and authorization.search(clause):
                require(
                    negation.search(clause) is not None,
                    "non-EU profile authorization",
                )


def run_guardrail(root: Path) -> None:
    raw = read(root, CONFIG)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        fail("valid JSON")
    require(type(data) is dict, "JSON object")
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
        "pricing_verified_at": "2026-07-21T11:29:41Z",
        "destination_regions_snapshot": [
            "eu-central-1",
            "eu-north-1",
            "eu-west-1",
            "eu-west-3",
        ],
    }
    for key, value in expected.items():
        require(exact_value(data[key], value), key)
    require(exact_mapping(data["parameters"], PARAMETERS), "exact inert parameters")
    for key in ("pricing_verified_at", "availability_verified_at"):
        require(utc_timestamp(data[key]), key)
    sources = data["sources"]
    require(type(sources) is list and len(sources) >= 8, "official sources")
    require(all(official_url(item) for item in sources), "official AWS sources")
    pricing = data["pricing_snapshot"]
    require(exact_mapping(pricing, PRICING), "exact pricing snapshot")
    require(utc_timestamp(pricing["pricing_verified_at"]), "pricing snapshot timestamp")
    require(official_url(pricing["pricing_source"]), "pricing snapshot source")
    require(
        pricing["estimated_input_cost"] + pricing["estimated_output_cost"]
        == pricing["estimated_call_cost"]
        and pricing["hard_ceiling"] > pricing["estimated_call_cost"],
        "pricing arithmetic",
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
    validate_normative_document(doc)
    combined = raw + "\n" + strip_fenced_code_blocks(doc)
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
