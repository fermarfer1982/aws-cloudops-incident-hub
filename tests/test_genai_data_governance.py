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
    "README.md",
    "docs/v1.0.0-lab-release-and-rollback.md",
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
    mutate(
        repository,
        FILES[0],
        "clasificación desconocida implica\nrechazo antes de la inferencia",
        "clasificación desconocida se revisa después",
    )
    rejected(repository, "allowlist normative semantics")


def test_missing_pii_fail_closed_is_rejected(repository: Path):
    mutate(repository, FILES[0], "la ejecución falla\nde forma cerrada", "la ejecución continúa")
    rejected(repository, "section semantics PII y secretos")


def test_raw_response_persistence_is_rejected(repository: Path):
    mutate(repository, FILES[0], "| Respuesta bruta | No |", "| Respuesta bruta | Sí |")
    rejected(repository, "retention table semantics")


def test_missing_human_review_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "Revisor humano autorizado | Evaluar todas las afirmaciones",
        "Revisor opcional | Evaluar una muestra",
    )
    rejected(repository, "section semantics Acceso humano y responsabilidad")


def test_wa021_completion_must_be_synthetic_only(repository: Path):
    mutate(
        repository,
        FILES[1],
        "Completado para el alcance sintético de laboratorio",
        "Completado para todos los entornos",
    )
    rejected(repository, "WA-021 repository status consistency")


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
    rejected(repository, "section semantics Región y transferencia")


def test_granted_bedrock_iam_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "`bedrock:InvokeModel` no se\nconcede",
        "`bedrock:InvokeModel` se concede",
    )
    rejected(repository, "Bedrock IAM contradiction")


def test_message_free_input_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "Texto fijo de la fixture sintética; sin entrada libre",
        "Texto libre proporcionado por el usuario",
    )
    rejected(repository, "allowlist restriction semantics")


def test_site_real_location_is_rejected(repository: Path):
    mutate(repository, FILES[0], "nunca una sede real", "puede ser una sede real")
    rejected(repository, "allowlist restriction semantics")


def test_value_string_type_is_rejected(repository: Path):
    mutate(repository, FILES[0], "| `value` | number o null |", "| `value` | string |")
    rejected(repository, "allowlist type semantics")


def test_internal_classification_allowed_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "| Interna | Información operativa no pública | No |",
        "| Interna | Información operativa no pública | Sí |",
    )
    rejected(repository, "classification table semantics")


def test_second_allowed_classification_is_rejected(repository: Path):
    mutate(
        repository,
        FILES[0],
        "| Pública | Información publicable sin restricciones | No necesaria |",
        "| Pública | Información publicable sin restricciones | Sí |",
    )
    rejected(repository, "classification table semantics")


def test_ambiguous_classification_is_rejected(repository: Path):
    mutate(repository, FILES[0], "| Interna | Información operativa no pública | No |", "| Interna | Información operativa no pública | Depende |")
    rejected(repository, "classification table semantics")


def test_artifact_thirty_day_retention_is_rejected(repository: Path):
    mutate(repository, FILES[0], "Máximo 7 días", "Máximo 30 días")
    rejected(repository, "retention table semantics")


def test_raw_response_artifact_is_rejected(repository: Path):
    mutate(repository, FILES[0], "| Respuesta bruta | No | Memoria hasta validación y revisión autorizada |", "| Respuesta bruta | Sí | Persistente como artifact |")
    rejected(repository, "retention table semantics")


def test_concrete_region_approval_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Retención", "La región eu-west-1 queda aprobada.\n\n## Retención")
    rejected(repository, "region approval contradiction")


def test_model_approval_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Retención", "El modelo lab-model queda aprobado.\n\n## Retención")
    rejected(repository, "model approval contradiction")


def test_inference_profile_approval_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Retención", "Inference profile lab-profile aprobado.\n\n## Retención")
    rejected(repository, "model approval contradiction")


def test_additional_granted_iam_contradiction_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Retención", "Se concede `bedrock:InvokeModel` al rol GenAI.\n\n## Retención")
    rejected(repository, "Bedrock IAM contradiction")


def test_additional_production_ready_claim_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Retención", "El proyecto está production-ready.\n\n## Retención")
    rejected(repository, "production readiness contradiction")


def test_additional_internal_data_permission_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Retención", "Los datos internos están permitidos.\n\n## Retención")
    rejected(repository, "NO-GO contradiction")


def test_additional_inference_authorization_is_rejected(repository: Path):
    mutate(repository, FILES[0], "## Retención", "Esta PR autoriza la inferencia.\n\n## Retención")
    rejected(repository, "NO-GO contradiction")


def test_automatic_retry_is_rejected(repository: Path):
    mutate(repository, FILES[0], "7. No reintentar.", "7. Reintentar automáticamente.")
    rejected(repository, "incident response semantics")


def test_missing_incident_response_step_is_rejected(repository: Path):
    mutate(repository, FILES[0], "3. Eliminar temporales.\n", "")
    rejected(repository, "incident response semantics")


def test_cleanup_on_failure_removed_is_rejected(repository: Path):
    mutate(repository, FILES[0], "se borrarán tanto en éxito como en\nfallo", "se borrarán únicamente en éxito")
    rejected(repository, "section semantics Borrado y cleanup")


def test_keyword_only_policy_is_rejected(repository: Path):
    headings = "\n".join(f"## {heading}\nkeyword" for heading in (
        "Estado y autoridad", "Alcance autorizado", "Finalidad", "Clasificación",
        "Allowlist exacta de atributos", "Datos prohibidos", "PII y secretos",
        "Minimización", "Región y transferencia", "Retención", "Borrado y cleanup",
        "Logging y telemetría", "Acceso humano y responsabilidad", "Auditoría",
        "Incidentes de datos", "Revisión de la política", "Cierre de WA-021",
    ))
    (repository / FILES[0]).write_text("# Gobierno de datos para GenAI\n" + headings + "\n", encoding="utf-8")
    rejected(repository, "section semantics")


def test_keywords_in_appendix_do_not_replace_section_contract(repository: Path):
    mutate(
        repository,
        FILES[0],
        "No existe fallback hacia la serialización del incidente completo.",
        "\n",
    )
    path = repository / FILES[0]
    path.write_text(path.read_text(encoding="utf-8") + "\nFallback appendix: no existe fallback.\n", encoding="utf-8")
    rejected(repository, "section semantics Minimización")


def test_readme_pending_status_is_rejected(repository: Path):
    mutate(repository, FILES[5], "- [x] WA-021: clasificación y retención completadas para el laboratorio sintético; datos reales, privacidad organizativa y producción permanecen pendientes.", "- [ ] WA-021: definir clasificación y retención de datos.")
    rejected(repository, "WA-021 repository status consistency")


def test_release_pending_status_is_rejected(repository: Path):
    mutate(repository, FILES[6], "WA-021: clasificación y retención cerradas para el laboratorio sintético; datos reales, requisitos organizativos de privacidad y uso en producción permanecen pendientes.", "WA-021: clasificación, retención y requisitos de privacidad pendientes.")
    rejected(repository, "WA-021 repository status consistency")


def test_readme_production_completion_is_rejected(repository: Path):
    mutate(repository, FILES[5], "datos reales, privacidad organizativa y producción permanecen pendientes", "datos reales y producción aprobados")
    rejected(repository, "WA-021 repository status consistency")


def test_duplicate_classification_row_is_rejected(repository: Path):
    row = "| Interna | Información operativa no pública | No |"
    mutate(repository, FILES[0], row, row + "\n" + row)
    rejected(repository, "classification table semantics")


def test_duplicate_allowlist_row_is_rejected(repository: Path):
    row = "| `source` | string | Valor sintético fijo de una allowlist versionada |"
    mutate(repository, FILES[0], row, row + "\n" + row)
    rejected(repository, "allowlist table structure")


def test_duplicate_required_heading_is_rejected(repository: Path):
    path = repository / FILES[0]
    path.write_text(path.read_text(encoding="utf-8") + "\n## Retención\nDuplicada.\n", encoding="utf-8")
    rejected(repository, "duplicate heading Retención")


def test_additional_table_column_is_rejected(repository: Path):
    mutate(repository, FILES[0], "| Atributo | Tipo permitido | Restricción |", "| Atributo | Tipo permitido | Restricción | Extra |")
    rejected(repository, "allowlist table structure")
