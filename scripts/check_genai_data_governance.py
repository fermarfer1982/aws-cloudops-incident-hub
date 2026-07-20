#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ALLOWED_ATTRIBUTES = {"source", "site", "message", "value"}
REQUIRED_HEADINGS = (
    "# Gobierno de datos para GenAI",
    "## Estado y autoridad",
    "## Alcance autorizado",
    "## Finalidad",
    "## Clasificación",
    "## Allowlist exacta de atributos",
    "## Datos prohibidos",
    "## PII y secretos",
    "## Minimización",
    "## Región y transferencia",
    "## Retención",
    "## Borrado y cleanup",
    "## Logging y telemetría",
    "## Acceso humano y responsabilidad",
    "## Auditoría",
    "## Incidentes de datos",
    "## Revisión de la política",
    "## Cierre de WA-021",
)


def require(condition: bool, control: str) -> None:
    if not condition:
        raise SystemExit(f"GenAI data governance control failed: {control}")


def _read(path: Path, control: str) -> str:
    require(path.is_file(), control)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise SystemExit(f"GenAI data governance control failed: {control}") from None


def _section(document: str, heading: str) -> str:
    require(heading in document, f"missing heading {heading}")
    tail = document.split(heading, 1)[1]
    return tail.split("\n## ", 1)[0]


def run_guardrail(root: Path) -> None:
    policy = _read(root / "docs/genai-data-governance.md", "missing policy")
    backlog = _read(root / "docs/well-architected-backlog.md", "missing backlog")
    review = _read(root / "docs/well-architected-review.md", "missing review")
    design = _read(root / "docs/bedrock-incident-copilot.md", "missing design")
    adr = _read(
        root / "docs/adr/013-amazon-bedrock-incident-copilot.md",
        "missing ADR-013",
    )

    for heading in REQUIRED_HEADINGS:
        require(heading in policy, f"missing heading {heading}")

    require(
        "Aprobado para el alcance sintético de laboratorio al fusionarse esta política"
        in policy,
        "approval scope",
    )
    allowlist = _section(policy, "## Allowlist exacta de atributos")
    attributes = re.findall(r"^\| `([^`]+)` \|", allowlist, flags=re.MULTILINE)
    require(len(attributes) == 4, "allowlist cardinality")
    require(set(attributes) == ALLOWED_ATTRIBUTES, "exact attribute allowlist")
    require(
        "La única clasificación admitida es **Sintética de laboratorio**" in policy,
        "synthetic-only classification",
    )
    require(
        "Campo no allowlisted o clasificación desconocida implica rechazo antes de la"
        in policy,
        "unknown-field rejection",
    )
    require(
        "no se invoca el modelo, la ejecución falla\nde forma cerrada" in policy,
        "PII and secret fail-closed",
    )
    retention = _section(policy, "## Retención")
    for row in (
        "| Prompt y contexto construidos | No |",
        "| Respuesta bruta | No |",
        "| Texto generado | No |",
        "| Artifact técnico | Solo evidencia saneada | Máximo 7 días |",
    ):
        require(row in retention, f"retention rule {row}")
    require("tanto en éxito como en\nfallo" in policy, "cleanup on success and failure")
    require(
        "Revisor humano autorizado | Evaluar todas las afirmaciones" in policy,
        "mandatory human review",
    )
    require("no autorizan ejecutar la inferencia" in policy, "no inference authorization")
    require("datos empresariales o incidentes reales" in policy, "real data prohibited")
    require(
        "Esta política no aprueba todavía ninguna región ni modelo" in policy,
        "region and model not approved",
    )
    require("`bedrock:InvokeModel` no se\nconcede" in policy, "Bedrock IAM not granted")
    require("- **Estado:** Proposed" in adr, "ADR-013 remains Proposed")
    require(
        "Completado para el alcance sintético de laboratorio" in backlog
        and "Datos reales, región, modelo, IAM Bedrock e inferencia continúan prohibidos"
        in backlog,
        "WA-021 synthetic-only completion",
    )
    link = "[política de gobierno de datos GenAI](genai-data-governance.md)"
    require(link in review, "review policy link")
    require(link in design, "design policy link")
    require(
        "**Production readiness:** Not production-ready" in review,
        "project not production-ready",
    )
    require("not production-ready" in review.lower(), "project not production-ready")
    require("not production-ready" in design.lower(), "design not production-ready")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_guardrail(args.root.resolve())
    print("GenAI data governance guardrail passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
