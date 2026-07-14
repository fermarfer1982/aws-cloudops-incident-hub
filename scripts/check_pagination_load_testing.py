#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGINATION = ROOT / "backend" / "app" / "pagination.py"
MAIN = ROOT / "backend" / "app" / "main.py"
FRONTEND = ROOT / "frontend" / "app.js"
PERFORMANCE = ROOT / "infrastructure" / "cloudops_infra" / "performance.py"
INFRA_TEST = ROOT / "infrastructure" / "tests" / "test_pagination.py"
API_TEST = ROOT / "tests" / "test_pagination.py"
LOAD_TEST = ROOT / "scripts" / "run_load_test.py"
GUIDE = ROOT / "docs" / "pagination-load-testing.md"
BASELINE = ROOT / "docs" / "performance-baseline.md"
LOCAL_EVIDENCE = ROOT / "docs" / "performance-baseline-local-2026-07-10.md"
AWS_EVIDENCE = ROOT / "docs" / "performance-baseline-aws-2026-07-12.md"
ADR = ROOT / "docs" / "adr" / "010-cursor-pagination-and-load-testing.md"
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def require_tokens(path: Path, tokens: tuple[str, ...]) -> None:
    content = path.read_text(encoding="utf-8")
    for token in tokens:
        require(token in content, f"{path} missing required token: {token}")


def main() -> None:
    paths = (
        PAGINATION,
        MAIN,
        FRONTEND,
        PERFORMANCE,
        INFRA_TEST,
        API_TEST,
        LOAD_TEST,
        GUIDE,
        BASELINE,
        LOCAL_EVIDENCE,
        AWS_EVIDENCE,
        ADR,
        WORKFLOW,
    )
    for path in paths:
        require(path.is_file(), f"Missing pagination/load-test artifact: {path}")

    require_tokens(
        PAGINATION,
        (
            "LastEvaluatedKey",
            "ExclusiveStartKey",
            "InvalidContinuationToken",
            "MAX_CONTINUATION_TOKEN_LENGTH = 4096",
            "context",
            "ScanIndexForward",
        ),
    )
    pagination_text = PAGINATION.read_text(encoding="utf-8")
    require(".scan(" not in pagination_text, "Pagination must not use DynamoDB Scan")

    require_tokens(
        MAIN,
        (
            'version="0.4.0"',
            'expose_headers=["X-Next-Token"]',
            "next_token",
            'response.headers["X-Next-Token"]',
            'status_code=400, detail="Invalid continuation token"',
        ),
    )
    require_tokens(
        FRONTEND,
        (
            "loadApiIncidents",
            'response.headers.get("x-next-token")',
            'url.searchParams.set("next_token", nextToken)',
        ),
    )
    require_tokens(
        PERFORMANCE,
        (
            "CorsConfiguration.ExposeHeaders",
            "X-Next-Token",
        ),
    )
    require_tokens(
        INFRA_TEST,
        ("ExposeHeaders", "X-Next-Token"),
    )
    require_tokens(
        API_TEST,
        (
            "non_overlapping_pages",
            "rejects_malformed_token",
            "rejects_token_reused_with_other_filters",
        ),
    )
    require_tokens(
        LOAD_TEST,
        (
            "httpx.AsyncClient",
            "requests_per_second",
            '"p50"',
            '"p95"',
            '"p99"',
            'default=0.0',
            "LOAD_TEST_BEARER_TOKEN",
            "thresholds_passed",
        ),
    )
    require_tokens(
        GUIDE,
        (
            "X-Next-Token",
            "LastEvaluatedKey",
            "ExclusiveStartKey",
            "read-only",
            "A validated local baseline was executed on 2026-07-10",
            "WA-017 is complete for the controlled local and AWS laboratory baselines",
        ),
    )
    require_tokens(
        BASELINE,
        (
            "Not measured yet",
            "must not be populated with estimated or invented results",
            "JSON report",
        ),
    )
    require_tokens(
        LOCAL_EVIDENCE,
        (
            "Measured and validated for the local Docker laboratory",
            "158.18 req/s",
            "159.38 req/s",
            "150.29 req/s",
            "0.0%",
            "365",
            "Duplicate IDs | 0",
            "does not measure",
            "validated AWS baseline",
            "WA-017 is closed",
        ),
    )
    require_tokens(
        AWS_EVIDENCE,
        (
            "Measured and validated for one controlled ephemeral AWS laboratory run",
            "29185526945",
            "Requests | 152",
            "5.01 req/s",
            "0.0%",
            "Was stack removal verified?",
            "WA-017",
            "WA-018",
        ),
    )
    require_tokens(
        ADR,
        (
            "ADR-010",
            "Response body remains a JSON array",
            "one bounded DynamoDB Query",
            "WA-016",
        ),
    )
    require_tokens(
        WORKFLOW,
        (
            "python scripts/run_load_test.py --help",
            "python scripts/check_pagination_load_testing.py",
        ),
    )

    print("Pagination and load-testing guardrails passed")


if __name__ == "__main__":
    main()
