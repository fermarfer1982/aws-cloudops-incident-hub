from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_bedrock_model_selection import run_guardrail

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "config/bedrock-model-selection.json",
    "docs/bedrock-model-selection.md",
    "docs/adr/013-amazon-bedrock-incident-copilot.md",
    "docs/well-architected-review.md",
    "scripts/check_bedrock_model_selection.py",
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    for relative in FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def config(root: Path) -> dict:
    return json.loads((root / FILES[0]).read_text(encoding="utf-8"))


def write(root: Path, data: dict) -> None:
    (root / FILES[0]).write_text(json.dumps(data), encoding="utf-8")


def rejected(root: Path, control: str) -> None:
    with pytest.raises(SystemExit, match=control):
        run_guardrail(root)


def mutate_doc(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_current_configuration_is_valid():
    run_guardrail(ROOT)


@pytest.mark.parametrize(
    ("key", "value", "control"),
    [
        ("source_region", "eu-west-2", "source_region"),
        ("regional_model_id", "amazon.nova-pro-v1:0", "regional_model_id"),
        (
            "geo_inference_profile_id",
            "eu.amazon.nova-pro-v1:0",
            "geo_inference_profile_id",
        ),
        (
            "geo_inference_profile_id",
            "global.amazon.nova-lite-v1:0",
            "geo_inference_profile_id",
        ),
        (
            "geo_inference_profile_id",
            "us.amazon.nova-lite-v1:0",
            "geo_inference_profile_id",
        ),
        (
            "geo_inference_profile_id",
            "apac.amazon.nova-lite-v1:0",
            "geo_inference_profile_id",
        ),
        ("provider", "anthropic", "provider"),
        ("endpoint", "bedrock", "endpoint"),
        ("api", "InvokeModel", "api"),
        ("api", "ConverseStream", "api"),
        ("streaming", True, "streaming"),
        ("enabled", True, "enabled"),
        ("iam_authorized", True, "iam_authorized"),
        ("model_access_verified_in_account", True, "model_access_verified_in_account"),
        ("fallback_model", "amazon.nova-pro-v1:0", "fallback_model"),
        ("fallback_region", "eu-west-3", "fallback_region"),
        ("input_modality", "image", "input_modality"),
    ],
)
def test_selection_mutations_are_rejected(
    repository: Path, key: str, value: object, control: str
):
    data = config(repository)
    assert data[key] != value
    data[key] = value
    write(repository, data)
    rejected(repository, control)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("automatic_retries", 1),
        ("tools", True),
        ("images", True),
        ("documents", True),
        ("video", True),
        ("caching", True),
        ("guardrails", True),
        ("application_inference_profile", True),
    ],
)
def test_inert_parameter_mutations_are_rejected(
    repository: Path, key: str, value: object
):
    data = config(repository)
    assert data["parameters"][key] != value
    data["parameters"][key] = value
    write(repository, data)
    rejected(repository, "exact inert parameters")


def test_missing_date_is_rejected(repository: Path):
    data = config(repository)
    del data["pricing_verified_at"]
    write(repository, data)
    rejected(repository, "exact configuration keys")


def test_invalid_date_is_rejected(repository: Path):
    data = config(repository)
    data["pricing_verified_at"] = "tomorrow"
    write(repository, data)
    rejected(repository, "pricing_verified_at")


def test_non_official_source_is_rejected(repository: Path):
    data = config(repository)
    data["sources"][0] = "https://example.com/model"
    write(repository, data)
    rejected(repository, "official AWS sources")


def test_additional_key_is_rejected(repository: Path):
    data = config(repository)
    data["approved"] = True
    write(repository, data)
    rejected(repository, "exact configuration keys")


def test_missing_key_is_rejected(repository: Path):
    data = config(repository)
    del data["provider"]
    write(repository, data)
    rejected(repository, "exact configuration keys")


def test_invalid_json_is_rejected(repository: Path):
    (repository / FILES[0]).write_text("{", encoding="utf-8")
    rejected(repository, "valid JSON")


def test_production_approval_is_rejected(repository: Path):
    mutate_doc(repository, FILES[1], "not production-ready", "production-ready")
    rejected(repository, "documentation: not production-ready")


def test_adr_acceptance_is_rejected(repository: Path):
    mutate_doc(repository, FILES[2], "- **Estado:** Proposed", "- **Estado:** Accepted")
    rejected(repository, "ADR-013 remains Proposed")


def test_inference_authorization_is_rejected(repository: Path):
    mutate_doc(
        repository,
        FILES[1],
        "NO-GO PARA INFERENCIA BEDROCK REAL",
        "AUTORIZADA PARA INFERENCIA",
    )
    rejected(repository, "no inference authorization")


def test_bedrock_permission_is_rejected(repository: Path):
    path = repository / FILES[1]
    path.write_text(
        path.read_text(encoding="utf-8") + "\nbedrock:InvokeModel\n", encoding="utf-8"
    )
    rejected(repository, "no Bedrock permission")


def test_documentation_contradiction_is_rejected(repository: Path):
    mutate_doc(repository, FILES[1], "no hay autorización IAM", "hay autorización IAM")
    rejected(repository, "documentation: no hay autorización IAM")


def test_root_is_isolated(repository: Path):
    result = subprocess.run(
        [sys.executable, str(repository / FILES[4]), "--root", str(repository)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "Bedrock model selection controls passed.\n"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("input_price_per_million_tokens", 999.0),
        ("output_price_per_million_tokens", 999.0),
        ("input_price_per_thousand_tokens", 999.0),
        ("output_price_per_thousand_tokens", 999.0),
        ("currency", "EUR"),
        ("pricing_unit", "per token"),
        ("max_input_tokens", 999),
        ("max_output_tokens", 999),
        ("estimated_call_cost", 0.000132),
        ("hard_ceiling", 0.0001),
        ("snapshot_only", False),
        ("service_tier", "flex"),
        ("pricing_verified_at", "tomorrow"),
        ("pricing_source", "https://example.com/pricing"),
    ],
)
def test_pricing_mutations_are_rejected(repository: Path, key: str, value: object):
    data = config(repository)
    assert data["pricing_snapshot"][key] != value
    data["pricing_snapshot"][key] = value
    write(repository, data)
    rejected(repository, "exact pricing snapshot")


def test_additional_pricing_key_is_rejected(repository: Path):
    data = config(repository)
    data["pricing_snapshot"]["approved"] = True
    assert "approved" in data["pricing_snapshot"]
    write(repository, data)
    rejected(repository, "exact pricing snapshot")


def test_missing_pricing_key_is_rejected(repository: Path):
    data = config(repository)
    del data["pricing_snapshot"]["currency"]
    assert "currency" not in data["pricing_snapshot"]
    write(repository, data)
    rejected(repository, "exact pricing snapshot")


@pytest.mark.parametrize(
    ("section", "key", "value", "control"),
    [
        ("parameters", "automatic_retries", False, "exact inert parameters"),
        ("parameters", "max_tokens", True, "exact inert parameters"),
        ("parameters", "temperature", False, "exact inert parameters"),
        ("parameters", "tools", 0, "exact inert parameters"),
        ("pricing_snapshot", "max_input_tokens", False, "exact pricing snapshot"),
        ("pricing_snapshot", "max_output_tokens", "300", "exact pricing snapshot"),
        ("pricing_snapshot", "snapshot_only", 1, "exact pricing snapshot"),
    ],
)
def test_strict_json_types_are_enforced(
    repository: Path, section: str, key: str, value: object, control: str
):
    data = config(repository)
    assert type(data[section][key]) is not type(value)
    data[section][key] = value
    write(repository, data)
    rejected(repository, control)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@docs.aws.amazon.com/path",
        "https://user@docs.aws.amazon.com/path",
        "https://docs.aws.amazon.com:443/path",
        "https://docs.aws.amazon.com.evil.test/path",
        "https://aws.example.com/path",
        "http://docs.aws.amazon.com/path",
        "https://amazonaws.example/path",
        "https://docs.aws.amazon.com/path\nheader: value",
    ],
)
def test_confusing_or_credentialed_sources_are_rejected(repository: Path, url: str):
    data = config(repository)
    data["sources"][0] = url
    assert data["sources"][0] == url
    write(repository, data)
    rejected(repository, "official AWS sources")


@pytest.mark.parametrize(
    "assertion",
    [
        "El perfil global está permitido.",
        "Se permite usar un perfil global.",
        "Puede utilizarse global.amazon.nova-lite-v1:0.",
        "La cuenta tiene garantizadas 400 solicitudes por minuto.",
        "La cuota de la cuenta está verificada.",
        "La capacidad disponible está garantizada.",
        "Todos los datos permanecen en Irlanda.",
        "Los datos nunca salen de eu-west-1.",
        "El procesamiento ocurre exclusivamente en Irlanda.",
        "La inferencia es estrictamente in-region.",
        "La inferencia está autorizada.",
        "IAM está autorizado.",
        "El acceso de cuenta está verificado.",
        "Producción está aprobada.",
        "ADR-013 está Accepted.",
        "El modelo está habilitado.",
        "La ejecución está permitida.",
        "Retry automático está habilitado.",
        "Fallback está permitido.",
    ],
)
def test_normative_contradictions_are_rejected(repository: Path, assertion: str):
    path = repository / FILES[1]
    path.write_text(
        path.read_text(encoding="utf-8") + "\n" + assertion, encoding="utf-8"
    )
    assert assertion in path.read_text(encoding="utf-8")
    rejected(repository, "documentation contradiction")


def test_contradiction_inside_fenced_example_is_ignored(repository: Path):
    path = repository / FILES[1]
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n```text\nTodos los datos permanecen en Irlanda.\n```\n",
        encoding="utf-8",
    )
    run_guardrail(repository)


def test_unterminated_fence_is_rejected(repository: Path):
    path = repository / FILES[1]
    path.write_text(path.read_text(encoding="utf-8") + "\n```text\n", encoding="utf-8")
    rejected(repository, "unterminated fenced code block")


def test_official_source_query_and_fragment_are_allowed(repository: Path):
    data = config(repository)
    data["sources"][0] = "https://docs.aws.amazon.com/path?view=1#section"
    write(repository, data)
    run_guardrail(repository)


def test_reordered_json_keys_are_allowed(repository: Path):
    data = config(repository)
    reordered = dict(reversed(list(data.items())))
    assert list(reordered) != list(data)
    write(repository, reordered)
    run_guardrail(repository)


def test_crlf_document_is_allowed(repository: Path):
    path = repository / FILES[1]
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    run_guardrail(repository)
