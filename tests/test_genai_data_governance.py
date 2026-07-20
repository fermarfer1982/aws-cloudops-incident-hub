from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.check_genai_data_governance import run_guardrail

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "docs/genai-data-governance.md",
    "docs/well-architected-backlog.md",
    "docs/well-architected-review.md",
    "docs/bedrock-incident-copilot.md",
    "docs/adr/013-amazon-bedrock-incident-copilot.md",
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    for relative in FILES:
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tmp_path


def mutate(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def rejected(root: Path, control: str) -> None:
    with pytest.raises(SystemExit, match=control):
        run_guardrail(root)


def test_current_repository_is_valid():
    run_guardrail(ROOT)


def test_missing_policy_is_rejected(repository: Path):
    (repository / "docs/genai-data-governance.md").unlink()
    rejected(repository, "missing policy")


def test_missing_required_heading_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Auditoría", "## Registro")
    rejected(repository, "missing heading")


def test_additional_allowed_attribute_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "| `value` | number o null | Valor sintético acotado; nunca texto |",
        "| `value` | number o null | Valor sintético acotado; nunca texto |\n"
        "| `hostname` | string | Sintético |",
    )
    rejected(repository, "allowlist cardinality")


def test_missing_allowed_attribute_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "| `value` | number o null | Valor sintético acotado; nunca texto |\n",
        "",
    )
    rejected(repository, "allowlist cardinality")


def test_unknown_field_without_rejection_is_rejected(repository: Path):
    mutate(repository, FILES[0], "implica rechazo antes de la\n> inferencia", "se revisa después")
    rejected(repository, "unknown-field rejection")


def test_missing_pii_fail_closed_is_rejected(repository: Path):
    mutate(repository, FILES[0], "la ejecución falla\nde forma cerrada", "la ejecución continúa")
    rejected(repository, "PII and secret fail-closed")


def test_raw_response_persistence_is_rejected(repository: Path):
    mutate(repository, FILES[0], "| Respuesta bruta | No |", "| Respuesta bruta | Sí |")
    rejected(repository, "retention rule")


def test_missing_human_review_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "Revisor humano autorizado | Evaluar todas las afirmaciones",
        "Revisor opcional | Evaluar una muestra",
    )
    rejected(repository, "mandatory human review")


def test_wa021_completion_must_be_synthetic_only(repository: Path):
    mutate(
        repository,
        FILES[1],
        "Completado para el alcance sintético de laboratorio",
        "Completado para todos los entornos",
    )
    rejected(repository, "WA-021 synthetic-only completion")


def test_adr013_must_remain_proposed(repository: Path):
    mutate(repository, FILES[4], "- **Estado:** Proposed", "- **Estado:** Accepted")
    rejected(repository, "ADR-013 remains Proposed")


def test_production_ready_claim_is_rejected(repository: Path):
    mutate(repository, FILES[2], "Not production-ready", "Production-ready")
    rejected(repository, "project not production-ready")


def test_approved_region_or_model_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "Esta política no aprueba todavía ninguna región ni modelo",
        "Esta política aprueba una región y un modelo",
    )
    rejected(repository, "region and model not approved")


def test_granted_bedrock_iam_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "`bedrock:InvokeModel` no se\nconcede",
        "`bedrock:InvokeModel` se concede",
    )
    rejected(repository, "Bedrock IAM not granted")
