#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY_MODULE = ROOT / "infrastructure" / "cloudops_infra" / "security.py"
APP = ROOT / "infrastructure" / "app.py"
TESTS = ROOT / "infrastructure" / "tests" / "test_security.py"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
CODEQL = ROOT / ".github" / "workflows" / "codeql.yml"
SBOM = ROOT / ".github" / "workflows" / "sbom.yml"
VALIDATE = ROOT / ".github" / "workflows" / "validate.yml"
SECRET_GUARD = ROOT / "scripts" / "check_repository_secrets.py"
SECURITY_POLICY = ROOT / "SECURITY.md"
SUMMARY = ROOT / "docs" / "p1-operational-security-supply-chain.md"
ADR = ROOT / "docs" / "adr" / "009-operational-security-supply-chain.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def read(path: Path) -> str:
    require(path.is_file(), f"Missing security artifact: {path}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    security_module = read(SECURITY_MODULE)
    app = read(APP)
    tests = read(TESTS)
    dependabot = read(DEPENDABOT)
    codeql = read(CODEQL)
    sbom = read(SBOM)
    validate = read(VALIDATE)
    secret_guard = read(SECRET_GUARD)
    security_policy = read(SECURITY_POLICY)
    summary = read(SUMMARY)
    adr = read(ADR)

    for token in (
        "default_route_settings",
        "throttling_rate_limit",
        "throttling_burst_limit",
        "DEFAULT_API_RATE_LIMIT = 10.0",
        "DEFAULT_API_BURST_LIMIT = 20",
    ):
        require(token in security_module, f"API throttling implementation missing: {token}")

    for token in (
        "api_throttling_rate_limit",
        "api_throttling_burst_limit",
        "apply_operational_security_controls",
        "positive_float_context",
        "positive_int_context",
    ):
        require(token in app, f"CDK app missing security context: {token}")

    for token in (
        "AWS::ApiGatewayV2::Stage",
        "ThrottlingRateLimit",
        "ThrottlingBurstLimit",
        "test_invalid_throttling_limits_are_rejected",
    ):
        require(token in tests, f"Security tests missing assertion: {token}")

    require("version: 2" in dependabot, "Dependabot schema version is missing")
    for ecosystem in ("pip", "docker", "github-actions"):
        require(
            f"package-ecosystem: {ecosystem}" in dependabot,
            f"Dependabot does not cover {ecosystem}",
        )
    require("directory: /backend" in dependabot, "Backend dependencies are not covered")
    require(
        "directory: /infrastructure" in dependabot,
        "Infrastructure dependencies are not covered",
    )

    for token in (
        "security-events: write",
        "github/codeql-action/init@v3",
        "github/codeql-action/analyze@v3",
        "languages: python",
        "queries: security-extended",
    ):
        require(token in codeql, f"CodeQL workflow missing control: {token}")
    require("pull_request_target" not in codeql, "CodeQL must not use pull_request_target")

    for token in (
        "anchore/sbom-action@v0.24.0",
        "format: spdx-json",
        "actions/upload-artifact@v4",
        "retention-days: 30",
        "dependency-snapshot: false",
    ):
        require(token in sbom, f"SBOM workflow missing control: {token}")
    require("pull_request_target" not in sbom, "SBOM workflow must not use pull_request_target")

    for token in (
        "AWS access key identifier",
        "private key header",
        "GitHub personal access token",
        "Potential secrets detected",
    ):
        require(token in secret_guard, f"Secret guardrail missing pattern: {token}")

    for phrase in (
        "Do not disclose exploitable details",
        "Revoke or rotate it immediately",
        "OIDC and temporary STS credentials",
    ):
        require(phrase in security_policy, f"Security policy missing concept: {phrase}")

    for phrase in (
        "10 requests/second",
        "CodeQL",
        "Dependabot",
        "secret scanning",
        "SPDX JSON",
        "not described as a replacement",
        "representative load tests",
    ):
        require(phrase in summary, f"Security documentation missing concept: {phrase}")

    require("Status: Accepted" in adr, "ADR-009 must be accepted")
    require("python scripts/check_repository_secrets.py" in validate, "CI does not scan secrets")
    require(
        "python scripts/check_security_supply_chain.py" in validate,
        "CI does not enforce supply-chain guardrails",
    )

    print("Operational security and supply-chain guardrails passed")


if __name__ == "__main__":
    main()
