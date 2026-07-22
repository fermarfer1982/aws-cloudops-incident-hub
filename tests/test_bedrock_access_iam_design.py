from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_bedrock_access_iam_design import run_guardrail

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "config/bedrock-access-readiness.json",
    "policies/bedrock-nova-lite-eu-invoke.template.json",
    "docs/bedrock-access-and-iam-design.md",
    "docs/bedrock-incident-copilot.md",
    "docs/well-architected-backlog.md",
    "docs/well-architected-review.md",
    "docs/adr/013-amazon-bedrock-incident-copilot.md",
    "scripts/check_bedrock_access_iam_design.py",
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    for relative in FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def load(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def write(root: Path, relative: str, value: object) -> None:
    (root / relative).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def rejected(root: Path, control: str) -> None:
    with pytest.raises(SystemExit, match=control):
        run_guardrail(root)


def append_doc(root: Path, text: str) -> None:
    path = root / FILES[2]
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_intact_temporary_copy_passes(repository: Path):
    run_guardrail(repository)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("enabled", True),
        ("iam_policy_applied", True),
        ("account_access_checked", True),
        ("account_access_verified", True),
        ("human_execution_approval", True),
        ("inference_authorized", True),
        ("terms_reviewed", True),
        ("streaming_action_allowed", True),
        ("scp_compatibility_checked", True),
        ("destination_regions_verified_for_execution", True),
        ("review_required_before_execution", False),
        ("status", "approved"),
        ("source_region", "eu-west-2"),
        ("model_id", "amazon.nova-pro-v1:0"),
        ("model_id", "amazon.nova-2-lite-v1:0"),
        ("inference_profile_id", "global.amazon.nova-lite-v1:0"),
        ("inference_profile_id", "us.amazon.nova-lite-v1:0"),
        ("inference_profile_id", "apac.amazon.nova-lite-v1:0"),
        ("api", "ConverseStream"),
        ("required_invoke_action", "bedrock:InvokeModelWithResponseStream"),
        ("required_invoke_action", "bedrock:InvokeModel*"),
        ("required_invoke_action", "bedrock:*"),
        ("required_invoke_action", "*"),
        ("enabled", 0),
        ("source_region", True),
    ],
)
def test_configuration_mutations_fail(repository: Path, key: str, value: object):
    data = load(repository, FILES[0])
    data[key] = value
    write(repository, FILES[0], data)
    rejected(repository, f"configuration {key}")


@pytest.mark.parametrize("mutation", ["extra", "missing", "invalid_json", "not_object"])
def test_configuration_shape_failures(repository: Path, mutation: str):
    path = repository / FILES[0]
    data = load(repository, FILES[0])
    if mutation == "extra":
        data["approved"] = True
        write(repository, FILES[0], data)
        rejected(repository, "exact configuration keys")
    elif mutation == "missing":
        del data["model_id"]
        write(repository, FILES[0], data)
        rejected(repository, "exact configuration keys")
    elif mutation == "invalid_json":
        path.write_text("{", encoding="utf-8")
        rejected(repository, "valid JSON")
    else:
        path.write_text("[]", encoding="utf-8")
        rejected(repository, "JSON object")


@pytest.mark.parametrize(
    ("value", "control"),
    [
        ("http://docs.aws.amazon.com/x", "official AWS sources"),
        ("https://example.com/x", "official AWS sources"),
        ("https://user@docs.aws.amazon.com/x", "official AWS sources"),
        ("https://user:pass@docs.aws.amazon.com/x", "official AWS sources"),
        ("https://docs.aws.amazon.com:443/x", "official AWS sources"),
        ("https://docs.aws.amazon.com.evil.example/x", "official AWS sources"),
        ("https://docs.aws.amazon.com", "official AWS sources"),
        (123, "official AWS sources"),
    ],
)
def test_untrusted_source_urls_fail(repository: Path, value: object, control: str):
    data = load(repository, FILES[0])
    data["sources"][0]["url"] = value
    write(repository, FILES[0], data)
    rejected(repository, control)


@pytest.mark.parametrize(
    "action",
    [
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:InvokeModel*",
        "bedrock:*",
        "*",
        "aws-marketplace:Subscribe",
        "iam:PassRole",
        "sts:AssumeRole",
        "organizations:DescribeOrganization",
        "cloudformation:CreateStack",
        "lambda:InvokeFunction",
        "s3:GetObject",
        "logs:PutLogEvents",
    ],
)
def test_extra_or_wrong_actions_fail(repository: Path, action: str):
    data = load(repository, FILES[1])
    data["policy_template"]["Statement"][0]["Action"] = action
    write(repository, FILES[1], data)
    rejected(repository, "exact least-privilege policy")


@pytest.mark.parametrize(
    "resource",
    [
        "*",
        "arn:${AWS_PARTITION}:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
        "arn:${AWS_PARTITION}:bedrock:eu-west-1::foundation-model/*",
        "arn:${AWS_PARTITION}:bedrock:${SOURCE_REGION}:${AWS_ACCOUNT_ID}:inference-profile/*",
        "arn:${AWS_PARTITION}:bedrock:${SOURCE_REGION}:${AWS_ACCOUNT_ID}:inference-profile/global.amazon.nova-lite-v1:0",
        "arn:${AWS_PARTITION}:bedrock:${SOURCE_REGION}:${AWS_ACCOUNT_ID}:inference-profile/us.amazon.nova-lite-v1:0",
        "arn:${AWS_PARTITION}:bedrock:${SOURCE_REGION}:${AWS_ACCOUNT_ID}:inference-profile/apac.amazon.nova-lite-v1:0",
        "arn:${AWS_PARTITION}:bedrock:${SOURCE_REGION}:${AWS_ACCOUNT_ID}:application-inference-profile/example",
        "arn:${AWS_PARTITION}:bedrock:eu-west-1::foundation-model/amazon.nova-pro-v1:0",
        "arn:${AWS_PARTITION}:bedrock:eu-west-1::foundation-model/amazon.nova-2-lite-v1:0",
        "arn:${AWS_PARTITION}:bedrock:eu-west-1::foundation-model/anthropic.example-v1:0",
        "arn:aws:bedrock:eu-west-1:123456789012:inference-profile/eu.amazon.nova-lite-v1:0",
        "arn:aws:iam::123456789012:role/example",
    ],
)
def test_wrong_profile_resource_fails(repository: Path, resource: str):
    data = load(repository, FILES[1])
    data["policy_template"]["Statement"][0]["Resource"] = resource
    write(repository, FILES[1], data)
    rejected(repository, "exact least-privilege policy")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_region",
        "additional_region",
        "wrong_region",
        "wrong_condition_key",
        "missing_condition",
        "wrong_condition_value",
        "principal",
        "role_arn",
        "wildcard_sid",
        "managed_policy",
        "wrong_placeholder",
        "applied_metadata",
        "enabled_metadata",
        "no_review",
    ],
)
def test_policy_structure_mutations_fail(repository: Path, mutation: str):
    data = load(repository, FILES[1])
    policy = data["policy_template"]
    statement = policy["Statement"][1]
    if mutation == "missing_region":
        statement["Resource"].pop()
    elif mutation == "additional_region":
        statement["Resource"].append(
            "arn:${AWS_PARTITION}:bedrock:eu-west-2::foundation-model/amazon.nova-lite-v1:0"
        )
    elif mutation == "wrong_region":
        statement["Resource"][0] = statement["Resource"][0].replace("eu-central-1", "eu-west-2")
    elif mutation == "wrong_condition_key":
        value = statement["Condition"]["StringEquals"].pop("bedrock:InferenceProfileArn")
        statement["Condition"]["StringEquals"]["aws:InferenceProfileArn"] = value
    elif mutation == "missing_condition":
        del statement["Condition"]
    elif mutation == "wrong_condition_value":
        statement["Condition"]["StringEquals"]["bedrock:InferenceProfileArn"] += "-other"
    elif mutation == "principal":
        statement["Principal"] = {"AWS": "${PRINCIPAL}"}
    elif mutation == "role_arn":
        statement["Resource"][0] = "arn:aws:iam::123456789012:role/example"
    elif mutation == "wildcard_sid":
        statement["Resource"][0] += "*"
    elif mutation == "managed_policy":
        data["metadata"]["managed_policy"] = "AmazonBedrockFullAccess"
    elif mutation == "wrong_placeholder":
        policy["Statement"][0]["Resource"] = policy["Statement"][0]["Resource"].replace("${AWS_ACCOUNT_ID}", "${ACCOUNT}")
    elif mutation == "applied_metadata":
        data["metadata"]["directive"] = "APPLY"
    elif mutation == "enabled_metadata":
        data["metadata"]["status"] = "enabled"
    else:
        data["metadata"]["human_review_required"] = False
    write(repository, FILES[1], data)
    rejected(repository, "(?:exact least-privilege policy|inert policy)")


@pytest.mark.parametrize(
    "claim",
    [
        "\nADR-013 is Accepted.\n",
        "\nThe project is production-ready.\n",
        "\nInference is authorized.\n",
        "\nLa inferencia está autorizada.\n",
        "\nIAM is applied.\n",
        "\nIAM está aplicado.\n",
        "\nAccount access is verified.\n",
        "\nEl acceso de la cuenta está verificado.\n",
        "\nSCP was modified.\n",
        "\nAmazonBedrockFullAccess is required.\n",
    ],
)
def test_documentary_contradictions_fail(repository: Path, claim: str):
    append_doc(repository, claim)
    rejected(repository, "contradictory")


@pytest.mark.parametrize(
    ("claim", "control"),
    [
        ("La política IAM ya está aplicada.", "contradictory IAM authorization"),
        ("La política se encuentra aplicada.", "contradictory IAM authorization"),
        ("IAM ha sido aplicado.", "contradictory IAM authorization"),
        ("El permiso ya está adjuntado al rol.", "contradictory IAM authorization"),
        ("La plantilla está desplegada.", "contradictory IAM authorization"),
        ('Resource "*" está permitido.', "contradictory wildcard authorization"),
        ('Se permite Resource: "*".', "contradictory wildcard authorization"),
        ("Puede usarse cualquier recurso.", "contradictory wildcard authorization"),
        ("Los wildcards de recurso están autorizados.", "contradictory wildcard authorization"),
        ("bedrock:* está permitido.", "contradictory wildcard authorization"),
        ("InvokeModel* está permitido.", "contradictory wildcard authorization"),
        ("Se permite InvokeModelWithResponseStream.", "contradictory streaming authorization"),
        ("El streaming está autorizado.", "contradictory streaming authorization"),
        ("Puede utilizarse ConverseStream.", "contradictory streaming authorization"),
        ("La aplicación podrá invocar respuestas en streaming.", "contradictory streaming authorization"),
        ("La plantilla puede aplicarse directamente.", "contradictory direct-apply authorization"),
        ("Puede desplegarse sin sustitución.", "contradictory direct-apply authorization"),
        ("No es necesaria revisión humana.", "contradictory direct-apply authorization"),
        ("La aprobación humana es opcional.", "contradictory direct-apply authorization"),
        ("DO_NOT_APPLY puede ignorarse.", "contradictory direct-apply authorization"),
        ("ListFoundationModels confirma que InvokeModel funcionará.", "contradictory catalog-access claim"),
        ("GetFoundationModel garantiza acceso efectivo.", "contradictory catalog-access claim"),
        ("GetFoundationModelAvailability garantiza acceso efectivo.", "contradictory catalog-access claim"),
        ("La disponibilidad del catálogo prueba que la cuenta puede invocar.", "contradictory catalog-access claim"),
        ("Una consulta de solo lectura demuestra autorización runtime.", "contradictory catalog-access claim"),
        ("Las SCP no afectan a cross-region inference.", "contradictory SCP or destination claim"),
        ("Puede omitirse una región de destino.", "contradictory SCP or destination claim"),
        ("No es necesario autorizar todos los destinos.", "contradictory SCP or destination claim"),
        ("Una región bloqueada no afecta a la solicitud.", "contradictory SCP or destination claim"),
        ("Las regiones opt-in deben estar siempre habilitadas manualmente para que el servicio pueda enrutar.", "contradictory SCP or destination claim"),
        ("El perfil Global está permitido.", "non-EU profile authorization"),
        ("El perfil US está autorizado.", "non-EU profile authorization"),
        ("Puede utilizarse un perfil estadounidense.", "non-EU profile authorization"),
        ("Se permite inferencia en Estados Unidos.", "non-EU profile authorization"),
        ("El perfil APAC está permitido.", "non-EU profile authorization"),
        ("Asia-Pacífico puede usarse como fallback.", "non-EU profile authorization"),
        ("La política runtime está aprobada para ejecución.", "contradictory execution authorization"),
        ("AmazonBedrockFullAccess está permitido para el runtime.", "contradictory execution authorization"),
        ("IAM no está aplicado; sin embargo, puede aplicarse directamente.", "contradictory direct-apply authorization"),
        ("Streaming no está permitido, pero ConverseStream queda autorizado.", "contradictory streaming authorization"),
        ("US está prohibido; no obstante, podrá usarse como contingencia.", "non-EU profile authorization"),
        ("ListFoundationModels no garantiza acceso, aunque confirma que InvokeModel funcionará.", "contradictory catalog-access claim"),
        ("Nota\n- El perfil Global está permitido.", "non-EU profile authorization"),
        ("Campo | Estado\nGlobal | permitido", "non-EU profile authorization"),
        ("EL   STREAMING   ESTÁ   AUTORIZADO!", "contradictory streaming authorization"),
    ],
)
def test_normative_bypasses_are_rejected(
    repository: Path, claim: str, control: str
):
    append_doc(repository, "\n" + claim + "\n")
    rejected(repository, control)


@pytest.mark.parametrize(
    "claim",
    [
        "La política IAM no está aplicada.",
        "La plantilla no debe aplicarse.",
        "IAM permanece sin aplicar.",
        "Los wildcards de recurso están prohibidos.",
        "Streaming no está permitido.",
        "InvokeModelWithResponseStream no está autorizado.",
        "Solo el perfil UE está permitido; US permanece prohibido.",
        "Ninguna consulta de catálogo garantiza invocación.",
    ],
)
def test_legitimate_prohibitions_are_accepted(repository: Path, claim: str):
    append_doc(repository, "\n" + claim + "\n")
    run_guardrail(repository)


@pytest.mark.parametrize(
    "mutation",
    [
        "additional",
        "missing",
        "duplicate",
        "altered_id",
        "completed",
        "evidence",
        "timestamp",
        "empty",
        "text",
        "completed_number",
        "completed_string",
        "top_level_number",
        "top_level_true",
        "iam_applied",
        "access_verified",
        "human_approval",
        "inference_authorized",
    ],
)
def test_readiness_checklist_mutations_are_rejected(
    repository: Path, mutation: str
):
    data = load(repository, FILES[0])
    checklist = data["readiness_checklist"]
    if mutation == "additional":
        checklist.append(copy.deepcopy(checklist[-1]))
        checklist[-1]["id"] = "unexpected_step"
    elif mutation == "missing":
        checklist.pop()
    elif mutation == "duplicate":
        checklist[1]["id"] = checklist[0]["id"]
    elif mutation == "altered_id":
        checklist[0]["id"] = "source_region_checked"
    elif mutation == "completed":
        checklist[0]["completed"] = True
    elif mutation == "evidence":
        checklist[0]["evidence"] = "claimed"
    elif mutation == "timestamp":
        checklist[0]["verified_at"] = "2026-07-22T00:00:00Z"
    elif mutation == "empty":
        data["readiness_checklist"] = []
    elif mutation == "text":
        data["readiness_checklist"] = "pending"
    elif mutation == "completed_number":
        checklist[0]["completed"] = 0
    elif mutation == "completed_string":
        checklist[0]["completed"] = "false"
    elif mutation == "top_level_number":
        data["iam_policy_applied"] = 0
    elif mutation == "top_level_true":
        data["iam_policy_applied"] = True
    else:
        step_id = {
            "iam_applied": "iam_policy_applied",
            "access_verified": "account_access_verified",
            "human_approval": "human_execution_approval",
            "inference_authorized": "inference_authorized",
        }[mutation]
        next(step for step in checklist if step["id"] == step_id)["completed"] = True
    write(repository, FILES[0], data)
    control = (
        "readiness step must remain incomplete"
        if mutation in {"completed", "evidence", "timestamp", "completed_number", "completed_string", "iam_applied", "access_verified", "human_approval", "inference_authorized"}
        else "(?:readiness checklist mismatch|configuration iam_policy_applied)"
    )
    rejected(repository, control)


def test_accepted_adr_fails(repository: Path):
    path = repository / FILES[6]
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("- **Estado:** Proposed", "- **Estado:** Accepted", 1), encoding="utf-8")
    rejected(repository, "ADR-013 remains Proposed")


def test_unterminated_fence_fails(repository: Path):
    append_doc(repository, "\n```json\n")
    rejected(repository, "unterminated fenced code block")


@pytest.mark.parametrize("variant", ["sorted", "crlf", "fenced", "source_order", "blocker_order", "whitespace"])
def test_semantically_valid_variants_pass(repository: Path, variant: str):
    if variant == "sorted":
        for relative in FILES[:2]:
            write(repository, relative, load(repository, relative))
    elif variant == "crlf":
        path = repository / FILES[2]
        path.write_bytes(path.read_text(encoding="utf-8").replace("\n", "\r\n").encode())
    elif variant == "fenced":
        append_doc(repository, "\n```text\nInference is authorized.\nResource: *\n```\n")
    elif variant == "source_order":
        data = load(repository, FILES[0])
        data["sources"].reverse()
        write(repository, FILES[0], data)
    elif variant == "blocker_order":
        data = load(repository, FILES[0])
        data["blockers"].reverse()
        write(repository, FILES[0], data)
    else:
        path = repository / FILES[2]
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    run_guardrail(repository)


def test_root_cli_is_isolated(repository: Path):
    result = subprocess.run(
        [sys.executable, str(repository / FILES[7]), "--root", str(repository)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "Bedrock access/IAM design controls passed.\n"


def test_mutation_does_not_touch_checkout(repository: Path):
    original = copy.deepcopy(load(ROOT, FILES[0]))
    data = load(repository, FILES[0])
    data["enabled"] = True
    write(repository, FILES[0], data)
    rejected(repository, "configuration enabled")
    assert load(ROOT, FILES[0]) == original
