#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / "docs" / "well-architected-review.md"
BACKLOG_PATH = ROOT / "docs" / "well-architected-backlog.md"
OWNERSHIP_PATH = ROOT / "docs" / "workload-ownership.md"
COST_EVIDENCE_PATH = ROOT / "docs" / "aws-cost-governance-evidence-2026-07-12.md"
ADR_PATH = ROOT / "docs" / "adr" / "005-well-architected-self-assessment.md"

PILLAR_HEADINGS = (
    "# 1. Operational excellence",
    "# 2. Security",
    "# 3. Reliability",
    "# 4. Performance efficiency",
    "# 5. Cost optimization",
    "# 6. Sustainability",
)

PRODUCTION_BLOCKERS = (
    "SEC-01",
    "SEC-02",
    "PERF-01",
    "PERF-02",
    "REL-01",
    "REL-02",
    "REL-03",
    "OPS-01",
    "OPS-02",
    "COST-01",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    for path in (
        REVIEW_PATH,
        BACKLOG_PATH,
        OWNERSHIP_PATH,
        COST_EVIDENCE_PATH,
        ADR_PATH,
    ):
        require(path.is_file(), f"Missing required Well-Architected artifact: {path}")

    review = REVIEW_PATH.read_text(encoding="utf-8")
    backlog = BACKLOG_PATH.read_text(encoding="utf-8")
    ownership = OWNERSHIP_PATH.read_text(encoding="utf-8")
    cost_evidence = COST_EVIDENCE_PATH.read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")

    for heading in PILLAR_HEADINGS:
        require(heading in review, f"Missing Well-Architected pillar heading: {heading}")

    for field in (
        "**Workload:**",
        "**Review type:**",
        "**Review date:**",
        "**Reviewer:**",
        "**Production readiness:**",
    ):
        require(field in review, f"Missing review metadata field: {field}")

    require(
        "not an AWS Well-Architected Tool review" in review,
        "The review must state that it is not an AWS Well-Architected Tool review",
    )
    require(
        "not production-ready" in review.lower(),
        "The production-readiness limitation must remain explicit",
    )
    require(
        "Accepted laboratory risks" in review,
        "The review must retain the accepted laboratory risks section",
    )

    for blocker in PRODUCTION_BLOCKERS:
        require(blocker in review, f"Missing production blocker in review: {blocker}")

    for phrase in (
        "Fernando Martínez Fernández",
        "Laboratory workload owner",
        "RACI matrix",
        "Decision authority",
        "No 24x7 on-call",
        "Production blockers",
        "Review cadence",
        "WA-010",
        "OPS-01",
    ):
        require(
            phrase in ownership,
            f"Missing required workload ownership concept: {phrase}",
        )

    require(
        "docs/workload-ownership.md" in review,
        "Well-Architected review must reference workload ownership evidence",
    )
    require(
        "Completado para repositorio y laboratorio" in backlog,
        "WA-010 laboratory completion must be recorded in the backlog",
    )

    for phrase in (
        "Validated for the AWS laboratory account",
        "cloudops-lab-monthly",
        "cloudops-zero-spend",
        "Cost Anomaly Detection",
        "WA-011",
        "COST-01",
    ):
        require(
            phrase in cost_evidence,
            f"Missing required cost-governance evidence concept: {phrase}",
        )

    require(
        "docs/aws-cost-governance-evidence-2026-07-12.md" in review,
        "Well-Architected review must reference cost-governance evidence",
    )
    require(
        "Completado para laboratorio: dos budgets" in backlog,
        "WA-011 laboratory completion must be recorded in the backlog",
    )

    backlog_ids = re.findall(r"^\| (WA-\d{3}) \|", backlog, flags=re.MULTILINE)
    require(len(backlog_ids) >= 25, "The remediation backlog is unexpectedly small")
    require(
        len(backlog_ids) == len(set(backlog_ids)),
        "Duplicate primary Well-Architected backlog identifiers found",
    )

    for priority in ("P0", "P1", "P2", "P3"):
        require(f"| {priority} |" in backlog, f"Missing backlog priority: {priority}")

    for phrase in (
        "Definition of done para producción",
        "Pendiente",
        "RTO",
        "RPO",
        "autenticación",
        "DynamoDB Scan",
        "AWS Budget",
    ):
        require(phrase in backlog, f"Missing required backlog concept: {phrase}")

    require(
        "No se asignará una puntuación numérica agregada" in adr,
        "ADR must reject unsupported aggregate scoring",
    )
    require(
        "no sustituye una revisión externa" in adr,
        "ADR must preserve the external-review limitation",
    )

    print("Well-Architected review guardrails passed")


if __name__ == "__main__":
    main()
