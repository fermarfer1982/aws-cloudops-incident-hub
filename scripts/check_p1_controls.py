#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELIABILITY = ROOT / "infrastructure" / "cloudops_infra" / "reliability.py"
APP = ROOT / "infrastructure" / "app.py"
TESTS = ROOT / "infrastructure" / "tests" / "test_reliability.py"
SUMMARY = ROOT / "docs" / "p1-reliability-operations.md"
OBJECTIVES = ROOT / "docs" / "recovery-objectives.md"
RESTORE = ROOT / "docs" / "runbook-dynamodb-restore.md"
SLOS = ROOT / "docs" / "service-level-objectives.md"
COSTS = ROOT / "docs" / "cost-controls.md"
COST_EVIDENCE = ROOT / "docs" / "aws-cost-governance-evidence-2026-07-12.md"
COST_EVIDENCE_JSON = ROOT / "docs" / "evidence" / "aws-cost-governance-2026-07-12.json"
ADR = ROOT / "docs" / "adr" / "008-optional-persistent-reliability-controls.md"
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    paths = (
        RELIABILITY,
        APP,
        TESTS,
        SUMMARY,
        OBJECTIVES,
        RESTORE,
        SLOS,
        COSTS,
        COST_EVIDENCE,
        COST_EVIDENCE_JSON,
        ADR,
        WORKFLOW,
    )
    for path in paths:
        require(path.is_file(), f"Missing required P1 artifact: {path}")

    reliability = RELIABILITY.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    summary = SUMMARY.read_text(encoding="utf-8")
    objectives = OBJECTIVES.read_text(encoding="utf-8")
    restore = RESTORE.read_text(encoding="utf-8")
    slos = SLOS.read_text(encoding="utf-8")
    costs = COSTS.read_text(encoding="utf-8")
    cost_evidence = COST_EVIDENCE.read_text(encoding="utf-8")
    cost_evidence_json = COST_EVIDENCE_JSON.read_text(encoding="utf-8")
    adr = ADR.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for token in (
        "point_in_time_recovery_specification",
        "PointInTimeRecoverySpecificationProperty",
        "RemovalPolicy.RETAIN",
        "retention_in_days = 30",
        "OperationsAlarmTopic",
        "EmailSubscription",
        "add_alarm_action",
        "add_ok_action",
    ):
        require(token in reliability, f"Reliability implementation missing token: {token}")

    for token in (
        "persistent_environment",
        "alarm_notification_email",
        "apply_reliability_controls",
        "persistent-reference",
    ):
        require(token in app, f"CDK app missing P1 context or application: {token}")

    for token in (
        "PointInTimeRecoveryEnabled",
        '"DeletionPolicy"] == "Retain"',
        '"RetentionInDays"] == 30',
        "AWS::SNS::Subscription",
        "AlarmActions",
        "OKActions",
    ):
        require(token in tests, f"P1 infrastructure tests missing assertion: {token}")

    for phrase in (
        "Incident data RPO",
        "15 minutes",
        "Single-Region service RTO",
        "60 minutes",
        "engineering targets",
        "not production-ready",
    ):
        require(phrase in summary, f"P1 summary missing concept: {phrase}")

    for phrase in (
        "Incident records RPO",
        "Incident service RTO",
        "game day",
        "rather than an SLA",
    ):
        require(phrase in objectives, f"Recovery objectives missing concept: {phrase}")

    for phrase in (
        "restore-table-to-point-in-time",
        "restores into new tables",
        "reviewed cutover change",
        "Post-cutover verification",
    ):
        require(phrase in restore, f"Restore runbook missing concept: {phrase}")

    for phrase in (
        "99.9%",
        "95% below 2 seconds",
        "99% persisted within 60 seconds",
        "error budget",
        "not contractual commitments",
    ):
        require(phrase in slos, f"SLO document missing concept: {phrase}")

    for phrase in (
        "AWS Budgets",
        "Cost Anomaly Detection",
        "Actual-spend notifications",
        "Forecasted-spend notification",
        "account or organization level",
    ):
        require(phrase in costs, f"Cost controls document missing concept: {phrase}")

    for phrase in (
        "Validated for the AWS laboratory account",
        "cloudops-lab-monthly",
        "cloudops-zero-spend",
        "cloudops-daily-anomalies",
        "WA-011",
        "COST-01",
        "not production-ready",
    ):
        require(
            phrase in cost_evidence,
            f"Cost-governance evidence missing concept: {phrase}",
        )

    for token in (
        '"account_id": "<redacted>"',
        '"contains_email_addresses": false',
        '"cloudops-lab-monthly"',
        '"cloudops-zero-spend"',
        '"cloudops-daily-anomalies"',
        '"status": "CONFIRMED"',
    ):
        require(
            token in cost_evidence_json,
            f"Sanitized cost-governance JSON missing token: {token}",
        )

    require(
        "651980295756" not in cost_evidence_json,
        "AWS account identifier must not be committed in cost evidence",
    )
    require(
        "@" not in cost_evidence_json,
        "Email addresses must not be committed in cost evidence",
    )

    require("ephemeral profile as the default" in adr, "ADR must preserve ephemeral default")
    require(
        "python scripts/check_p1_controls.py" in workflow,
        "CI does not enforce P1 guardrails",
    )

    print("P1 reliability and operations guardrails passed")


if __name__ == "__main__":
    main()
