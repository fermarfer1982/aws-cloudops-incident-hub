#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_PATH = ROOT / "governance" / "organization-blueprint.json"
SCP_PATH = ROOT / "governance" / "scps" / "deny-leaving-organization.json"
ARCHITECTURE_PATH = ROOT / "docs" / "multi-account-production-architecture.md"
MATRIX_PATH = ROOT / "docs" / "multi-account-control-matrix.md"
MIGRATION_PATH = ROOT / "docs" / "multi-account-migration-plan.md"
ADR_PATH = ROOT / "docs" / "adr" / "006-multi-account-production-landing-zone.md"

REQUIRED_OUS = {
    "Security",
    "Infrastructure",
    "Workloads-NonProduction",
    "Workloads-Production",
    "Sandbox",
    "Suspended",
}

REQUIRED_ACCOUNTS = {
    "management",
    "log-archive",
    "security-tooling",
    "shared-services",
    "network",
    "cloudops-dev",
    "cloudops-stage",
    "cloudops-prod",
    "sandbox-users",
}

NON_WORKLOAD_ACCOUNTS = {
    "management",
    "log-archive",
    "security-tooling",
    "shared-services",
    "network",
}

REQUIRED_PERMISSION_SETS = {
    "SecurityAudit",
    "PlatformAdministrator",
    "WorkloadDeveloperNonProd",
    "WorkloadOperatorReadOnly",
    "ProductionDeployer",
    "BillingReadOnly",
    "BreakGlassAdministrator",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"Missing required multi-account artifact: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    require(isinstance(data, dict), f"Expected a JSON object in {path}")
    return data


def load_text(path: Path) -> str:
    require(path.is_file(), f"Missing required multi-account artifact: {path}")
    return path.read_text(encoding="utf-8")


def validate_blueprint(blueprint: dict[str, Any]) -> None:
    require(
        blueprint.get("status") == "reference-blueprint-not-deployed",
        "Blueprint must remain explicitly marked as not deployed",
    )
    require(
        blueprint.get("primary_region") == "eu-west-1",
        "Primary Region changed without updating the blueprint guardrail",
    )

    organizational_units = blueprint.get("organizational_units")
    require(isinstance(organizational_units, list), "Missing organizational_units")
    ou_names = {
        item.get("name")
        for item in organizational_units
        if isinstance(item, dict)
    }
    require(REQUIRED_OUS <= ou_names, "Required organizational units are missing")

    accounts = blueprint.get("accounts")
    require(isinstance(accounts, list), "Missing accounts")
    account_records = {
        item.get("name"): item
        for item in accounts
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    require(REQUIRED_ACCOUNTS <= set(account_records), "Required accounts are missing")
    require(
        len(account_records) == len(accounts),
        "Duplicate or invalid account records found",
    )

    for account_name in NON_WORKLOAD_ACCOUNTS:
        require(
            account_records[account_name].get("workloads_allowed") is False,
            f"Foundational account unexpectedly allows workloads: {account_name}",
        )

    require(
        account_records["cloudops-dev"].get("ou") == "Workloads-NonProduction",
        "Dev account must remain in the non-production OU",
    )
    require(
        account_records["cloudops-stage"].get("ou") == "Workloads-NonProduction",
        "Stage account must remain in the non-production OU",
    )
    require(
        account_records["cloudops-prod"].get("ou") == "Workloads-Production",
        "Production account must remain isolated in the production OU",
    )

    identity = blueprint.get("identity")
    require(isinstance(identity, dict), "Missing identity design")
    require(
        identity.get("service") == "AWS IAM Identity Center organization instance",
        "Identity must use an organization instance of IAM Identity Center",
    )
    permission_sets = identity.get("permission_sets")
    require(isinstance(permission_sets, list), "Missing permission_sets")
    require(
        REQUIRED_PERMISSION_SETS <= set(permission_sets),
        "Required permission sets are missing",
    )

    deployment = blueprint.get("deployment")
    require(isinstance(deployment, dict), "Missing deployment design")
    require(
        deployment.get("authentication") == "GitHub OIDC",
        "Deployment authentication must remain GitHub OIDC",
    )
    require(
        deployment.get("promotion_path")
        == ["cloudops-dev", "cloudops-stage", "cloudops-prod"],
        "Promotion path must remain Dev to Stage to Prod",
    )

    scp_strategy = blueprint.get("scp_strategy")
    require(isinstance(scp_strategy, dict), "Missing SCP strategy")
    deployment_order = scp_strategy.get("deployment_order")
    require(isinstance(deployment_order, list), "Missing SCP deployment order")
    require(
        any("policy-staging OU" in item for item in deployment_order),
        "SCPs must be tested in a policy-staging OU",
    )

    production_gates = blueprint.get("production_readiness_gates")
    require(isinstance(production_gates, list), "Missing production readiness gates")
    require(
        len(production_gates) >= 8,
        "Production readiness gate list is unexpectedly small",
    )
    require(
        any("DynamoDB Scan" in item for item in production_gates),
        "Production gates must retain the no-Scan requirement",
    )


def validate_scp(scp: dict[str, Any]) -> None:
    require(scp.get("Version") == "2012-10-17", "Unexpected SCP version")
    statements = scp.get("Statement")
    require(isinstance(statements, list), "SCP Statement must be a list")
    require(len(statements) == 1, "Example SCP must remain intentionally minimal")
    statement = statements[0]
    require(isinstance(statement, dict), "Invalid SCP statement")
    require(statement.get("Effect") == "Deny", "SCP must use an explicit deny")
    require(
        statement.get("Action") == "organizations:LeaveOrganization",
        "Example SCP must only deny leaving the organization",
    )
    require(statement.get("Resource") == "*", "Unexpected SCP resource")


def validate_documents(
    architecture: str,
    matrix: str,
    migration: str,
    adr: str,
) -> None:
    for phrase in (
        "single AWS Organization",
        "Management account restrictions",
        "AWS IAM Identity Center",
        "Service control policy strategy",
        "Build once and promote immutable artifacts",
        "does not require a VPC",
        "Production promotion gates",
        "not deployed",
    ):
        require(phrase in architecture, f"Architecture missing concept: {phrase}")

    normalized_architecture = architecture.lower()
    for account in REQUIRED_ACCOUNTS:
        display_name = account.replace("-", " ")
        require(
            display_name in normalized_architecture,
            f"Architecture missing account: {account}",
        )

    for control_prefix in (
        "ORG-",
        "IAM-",
        "CICD-",
        "LOG-",
        "SEC-",
        "REL-",
        "PERF-",
        "COST-",
        "SUS-",
        "NET-",
    ):
        require(control_prefix in matrix, f"Control matrix missing domain: {control_prefix}")

    for phase in range(11):
        require(
            f"## Phase {phase}" in migration,
            f"Migration plan missing phase {phase}",
        )

    for phrase in (
        "Production and non-production data",
        "management account will not host application workloads",
        "GitHub OIDC",
        "SCPs will be introduced progressively",
        "does not authorize a production launch",
        "CI guardrail",
    ):
        require(phrase in adr, f"ADR missing decision constraint: {phrase}")


def main() -> None:
    blueprint = load_json(BLUEPRINT_PATH)
    scp = load_json(SCP_PATH)
    architecture = load_text(ARCHITECTURE_PATH)
    matrix = load_text(MATRIX_PATH)
    migration = load_text(MIGRATION_PATH)
    adr = load_text(ADR_PATH)

    validate_blueprint(blueprint)
    validate_scp(scp)
    validate_documents(architecture, matrix, migration, adr)
    print("Multi-account blueprint guardrails passed")


if __name__ == "__main__":
    main()
