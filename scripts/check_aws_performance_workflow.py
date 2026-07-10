#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aws-performance-ephemeral.yml"
VALIDATE = ROOT / ".github" / "workflows" / "validate.yml"
LOAD_TEST = ROOT / "scripts" / "run_load_test.py"
COLLECTOR = ROOT / "scripts" / "collect_aws_performance_evidence.py"
BOOTSTRAP = ROOT / "bootstrap" / "github-oidc-role.yml"
APP = ROOT / "infrastructure" / "app.py"
PERFORMANCE = ROOT / "infrastructure" / "cloudops_infra" / "aws_performance.py"
INFRA_TEST = ROOT / "infrastructure" / "tests" / "test_aws_performance.py"
GUIDE = ROOT / "docs" / "aws-performance-test.md"
ADR = ROOT / "docs" / "adr" / "011-controlled-ephemeral-aws-performance-test.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def require_tokens(path: Path, tokens: tuple[str, ...]) -> str:
    require(path.is_file(), f"Missing controlled AWS performance artifact: {path}")
    content = path.read_text(encoding="utf-8")
    for token in tokens:
        require(token in content, f"{path} missing required token: {token}")
    return content


def main() -> None:
    workflow = require_tokens(
        WORKFLOW,
        (
            "workflow_dispatch:",
            "RUN-EPHEMERAL-AWS-PERFORMANCE-TEST",
            "AWS_LOAD_TEST_APPROVED",
            "AWS_COST_CONTROLS_CONFIRMED",
            "environment: aws-ephemeral",
            "github.ref == 'refs/heads/main'",
            "id-token: write",
            "allowed-account-ids:",
            "enable_load_test_client=true",
            "--max-rps \"$MAX_RPS\"",
            "MAX_RPS 8",
            "cognito-idp describe-user-pool-client",
            "grant_type=client_credentials",
            "::add-mask::$CLIENT_SECRET",
            "::add-mask::$LOAD_TEST_BEARER_TOKEN",
            "collect_aws_performance_evidence.py",
            "sleep 120",
            "if: always() && steps.aws_credentials.outcome == 'success'",
            "cdk destroy",
            "Verify stack removal",
            "retention-days: 14",
            "Enforce test and cleanup outcomes",
        ),
    )
    require("\n  push:" not in workflow, "AWS performance workflow must not run on push")
    require("pull_request:" not in workflow, "AWS performance workflow must not run on PRs")
    require("schedule:" not in workflow, "AWS performance workflow must not be scheduled")
    require("workflow_call:" not in workflow, "AWS performance workflow must not be reusable")
    require("60\")" not in workflow, "Unexpected workflow text")
    require("case \"$DURATION_SECONDS\" in 15|30|60)" in workflow, "Duration hard cap missing")
    require("case \"$CONCURRENCY\" in 1|2|5)" in workflow, "Concurrency hard cap missing")
    require("case \"$MAX_RPS\" in 1|2|5|8)" in workflow, "Request-rate hard cap missing")
    require("case \"$WRITE_PERCENT\" in 0|1|5)" in workflow, "Write-percentage hard cap missing")
    require("/tmp/cloudops-token.json" in workflow, "Token response must remain temporary")
    require("evidence/cloudops-token.json" not in workflow, "Access token must not be uploaded")

    require_tokens(
        LOAD_TEST,
        (
            "class RateLimiter",
            "--max-rps",
            "LOAD_TEST_MAX_RPS",
            "max_requests_per_second",
            "await rate_limiter.wait()",
        ),
    )
    require_tokens(
        COLLECTOR,
        (
            "AWS/ApiGateway",
            "AWS/Lambda",
            "AWS/SQS",
            "AWS/DynamoDB",
            "IntegrationLatency",
            "ConcurrentExecutions",
            "ApproximateAgeOfOldestMessage",
            "ReadThrottleEvents",
            "WriteThrottleEvents",
            "metrics_without_datapoints",
        ),
    )
    require_tokens(
        BOOTSTRAP,
        (
            "cognito-idp:DescribeUserPoolClient",
            "cloudwatch:GetMetricData",
            "ReadEphemeralLoadTestClient",
            "ReadNativePerformanceMetrics",
        ),
    )
    require_tokens(
        APP,
        (
            "enable_load_test_client",
            "apply_aws_performance_controls",
        ),
    )
    require_tokens(
        PERFORMANCE,
        (
            "client_credentials",
            "generate_secret=True",
            "READ_SCOPE",
            "WRITE_SCOPE",
            "LoadTestClientId",
            "LoadTestTokenUrl",
            "ApiFunctionName",
            "ProcessorFunctionName",
        ),
    )
    require_tokens(
        INFRA_TEST,
        (
            "test_default_reference_does_not_create_machine_client",
            "test_ephemeral_performance_profile_creates_scoped_machine_client",
            "AllowedOAuthFlows",
            "GenerateSecret",
        ),
    )
    require_tokens(
        GUIDE,
        (
            "Prepared but not executed",
            "AWS_LOAD_TEST_APPROVED",
            "AWS_COST_CONTROLS_CONFIRMED",
            "8 requests/s",
            "15-minute access token",
            "No access token or client secret belongs in the artifact",
            "WA-017 remains open for AWS evidence",
        ),
    )
    require_tokens(
        ADR,
        (
            "ADR-011",
            "global request-start ceiling",
            "client-credentials grant",
            "Destroy the stack",
        ),
    )
    require_tokens(
        VALIDATE,
        (
            "python scripts/collect_aws_performance_evidence.py --help",
            "python scripts/check_aws_performance_workflow.py",
        ),
    )

    print("Controlled AWS performance workflow guardrails passed")


if __name__ == "__main__":
    main()
