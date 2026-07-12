#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

APP = ROOT / "infrastructure/app.py"
RELIABILITY = ROOT / "infrastructure/cloudops_infra/reliability.py"
TESTS = ROOT / "infrastructure/tests/test_reliability.py"
OBSERVABILITY = ROOT / "docs/observability.md"
P1 = ROOT / "docs/p1-reliability-operations.md"
BACKLOG = ROOT / "docs/well-architected-backlog.md"
ADR = ROOT / "docs/adr/012-amazon-q-slack-chatops.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    paths = (
        APP,
        RELIABILITY,
        TESTS,
        OBSERVABILITY,
        P1,
        BACKLOG,
        ADR,
    )

    for path in paths:
        require(path.is_file(), f"Missing ChatOps artifact: {path}")

    app = APP.read_text(encoding="utf-8")
    reliability = RELIABILITY.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    observability = OBSERVABILITY.read_text(encoding="utf-8")
    p1 = P1.read_text(encoding="utf-8")
    backlog = BACKLOG.read_text(encoding="utf-8")
    adr = ADR.read_text(encoding="utf-8")

    for token in (
        "slack_workspace_id",
        "slack_channel_id",
    ):
        require(token in app, f"Missing app ChatOps token: {token}")

    for token in (
        "SlackChannelConfiguration",
        "LoggingLevel.NONE",
        "user_role_required=False",
        "cloudwatch:Describe*",
        "cloudwatch:Get*",
        "cloudwatch:List*",
        "sns:GetTopicAttributes",
        "sns:List*",
        "slack_channel_configuration_arn",
    ):
        require(
            token in reliability,
            f"Missing reliability ChatOps token: {token}",
        )

    require(
        "AdministratorAccess" not in reliability,
        "ChatOps must not use AdministratorAccess",
    )

    for token in (
        "test_slack_creates_notification_only_chatops_configuration",
        "test_slack_identifiers_must_be_provided_together",
        "test_invalid_slack_identifier_prefixes_are_rejected",
    ):
        require(token in tests, f"Missing ChatOps test: {token}")

    require(
        "Perfil ChatOps opcional" in observability,
        "Missing ChatOps observability documentation",
    )
    require(
        "Real workspace and channel identifiers are not committed" in p1,
        "Missing ChatOps P1 documentation",
    )
    require(
        "evidencia ALARM/OK pendientes" in backlog,
        "WA-014 status is not updated",
    )
    require(
        "mínimo privilegio" in adr,
        "Missing least-privilege decision in ADR-012",
    )

    print("ChatOps architecture guardrails passed")


if __name__ == "__main__":
    main()
