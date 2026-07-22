#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path("config/bedrock-access-readiness.json")
POLICY = Path("policies/bedrock-nova-lite-eu-invoke.template.json")
DESIGN = Path("docs/bedrock-access-and-iam-design.md")
COPILOT = Path("docs/bedrock-incident-copilot.md")
BACKLOG = Path("docs/well-architected-backlog.md")
REVIEW = Path("docs/well-architected-review.md")
ADR = Path("docs/adr/013-amazon-bedrock-incident-copilot.md")

REGIONS = ["eu-central-1", "eu-north-1", "eu-west-1", "eu-west-3"]
PROFILE_ARN = (
    "arn:${AWS_PARTITION}:bedrock:${SOURCE_REGION}:${AWS_ACCOUNT_ID}:"
    "inference-profile/eu.amazon.nova-lite-v1:0"
)
MODEL_ARNS = [
    f"arn:${{AWS_PARTITION}}:bedrock:{region}::foundation-model/"
    "amazon.nova-lite-v1:0"
    for region in REGIONS
]
CONFIG_KEYS = {
    "account_access_checked",
    "account_access_verified",
    "api",
    "blockers",
    "destination_regions_snapshot",
    "destination_regions_verified_for_execution",
    "enabled",
    "human_execution_approval",
    "iam_policy_applied",
    "inference_authorized",
    "inference_profile_id",
    "model_id",
    "policy_version",
    "readiness_checklist",
    "required_invoke_action",
    "review_required_before_execution",
    "scp_compatibility_checked",
    "source_region",
    "sources",
    "status",
    "streaming_action_allowed",
    "terms_reviewed",
}
FALSE_GATES = {
    "account_access_checked",
    "account_access_verified",
    "destination_regions_verified_for_execution",
    "enabled",
    "human_execution_approval",
    "iam_policy_applied",
    "inference_authorized",
    "scp_compatibility_checked",
    "streaming_action_allowed",
    "terms_reviewed",
}
SOURCE_KEYS = {"interpretation", "uncertainty", "url", "verified_at"}
OFFICIAL_HOSTS = {"docs.aws.amazon.com", "aws.amazon.com"}
READINESS_STEPS = [
    "source_region_enabled_checked",
    "official_destinations_revalidated",
    "catalog_presence_checked",
    "regional_availability_checked",
    "runtime_identity_selected",
    "runtime_identity_validated",
    "rendered_policy_reviewed",
    "iam_policy_applied",
    "scp_compatibility_checked",
    "destination_regions_authorized",
    "account_access_checked",
    "account_access_verified",
    "terms_reviewed",
    "non_inference_precheck_completed",
    "human_execution_approval",
    "inference_authorized",
]
CHECKLIST_KEYS = {"completed", "evidence", "id", "verified_at"}


def fail(control: str) -> None:
    raise SystemExit(f"Bedrock access/IAM design control failed: {control}")


def require(value: bool, control: str) -> None:
    if not value:
        fail(control)


def read(root: Path, relative: Path) -> str:
    path = root / relative
    require(path.is_file(), f"missing {relative}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail(f"unreadable {relative}")


def load_json(root: Path, relative: Path) -> dict[str, object]:
    try:
        value = json.loads(read(root, relative))
    except json.JSONDecodeError:
        fail(f"valid JSON: {relative}")
    require(type(value) is dict, f"JSON object: {relative}")
    return value


def exact(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


def timestamp(value: object) -> bool:
    if type(value) is not str or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def official_url(value: object) -> bool:
    if type(value) is not str or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in OFFICIAL_HOSTS
        and parsed.username is None
        and parsed.password is None
        and port is None
        and bool(parsed.path)
    )


def strip_fences(document: str) -> str:
    output: list[str] = []
    active: tuple[str, int] | None = None
    opening = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\r\n]*(?:\r\n|\r|\n)?$")
    for line in document.splitlines(keepends=True):
        ending_match = re.search(r"(?:\r\n|\r|\n)$", line)
        ending = ending_match.group(0) if ending_match else ""
        if active is None:
            match = opening.fullmatch(line)
            if match:
                marker = match.group(1)
                active = (marker[0], len(marker))
                output.append(ending)
            else:
                output.append(line)
            continue
        closing = re.compile(
            rf"^ {{0,3}}{re.escape(active[0])}{{{active[1]},}}[ \t]*(?:\r\n|\r|\n)?$"
        )
        if closing.fullmatch(line):
            active = None
        output.append(ending)
    require(active is None, "unterminated fenced code block")
    return "".join(output)


def validate_config(data: dict[str, object]) -> None:
    require(set(data) == CONFIG_KEYS, "exact configuration keys")
    expected = {
        "api": "Converse",
        "destination_regions_snapshot": REGIONS,
        "inference_profile_id": "eu.amazon.nova-lite-v1:0",
        "model_id": "amazon.nova-lite-v1:0",
        "policy_version": "bedrock-access-readiness/v1",
        "required_invoke_action": "bedrock:InvokeModel",
        "review_required_before_execution": True,
        "source_region": "eu-west-1",
        "status": "proposed-disabled",
    }
    for key, value in expected.items():
        require(exact(data[key], value), f"configuration {key}")
    for key in FALSE_GATES:
        require(exact(data[key], False), f"configuration {key}")
    checklist = data["readiness_checklist"]
    require(type(checklist) is list, "readiness checklist mismatch")
    require(len(checklist) == len(READINESS_STEPS), "readiness checklist mismatch")
    for index, expected_id in enumerate(READINESS_STEPS):
        step = checklist[index]
        require(
            type(step) is dict and set(step) == CHECKLIST_KEYS,
            "readiness checklist mismatch",
        )
        require(exact(step["id"], expected_id), "readiness checklist mismatch")
        require(
            exact(step["completed"], False)
            and step["evidence"] is None
            and step["verified_at"] is None,
            "readiness step must remain incomplete",
        )
    checklist_by_id = {step["id"]: step["completed"] for step in checklist}
    for key in FALSE_GATES & set(checklist_by_id):
        require(
            exact(data[key], checklist_by_id[key]), "readiness checklist mismatch"
        )
    blockers = data["blockers"]
    require(type(blockers) is list and len(blockers) == 6, "exact blockers")
    require(
        all(type(item) is str and item.strip() for item in blockers), "blocker strings"
    )
    sources = data["sources"]
    require(type(sources) is list and len(sources) >= 5, "official AWS sources")
    for source in sources:
        require(type(source) is dict and set(source) == SOURCE_KEYS, "exact source keys")
        require(official_url(source["url"]), "official AWS sources")
        require(timestamp(source["verified_at"]), "source UTC timestamp")
        require(
            type(source["interpretation"]) is str
            and bool(source["interpretation"].strip()),
            "source interpretation",
        )
        require(
            type(source["uncertainty"]) is str and bool(source["uncertainty"].strip()),
            "source uncertainty",
        )


def validate_policy(data: dict[str, object]) -> None:
    require(set(data) == {"metadata", "policy_template"}, "inert policy envelope")
    require(
        data["metadata"]
        == {
            "directive": "DO_NOT_APPLY",
            "human_review_required": True,
            "status": "disabled",
        },
        "inert policy metadata",
    )
    expected = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": "bedrock:InvokeModel",
                "Effect": "Allow",
                "Resource": PROFILE_ARN,
                "Sid": "InvokeApprovedEuInferenceProfile",
            },
            {
                "Action": "bedrock:InvokeModel",
                "Condition": {
                    "StringEquals": {"bedrock:InferenceProfileArn": PROFILE_ARN}
                },
                "Effect": "Allow",
                "Resource": MODEL_ARNS,
                "Sid": "InvokeNovaLiteOnlyThroughApprovedProfile",
            },
        ],
    }
    require(data["policy_template"] == expected, "exact least-privilege policy")
    rendered = json.dumps(data, sort_keys=True)
    require("*" not in rendered, "no wildcards")
    require(
        all(token in rendered for token in ("${AWS_PARTITION}", "${SOURCE_REGION}", "${AWS_ACCOUNT_ID}")),
        "mandatory placeholders",
    )
    require(not re.search(r"(?<!\$\{)\b\d{12}\b", rendered), "no real account ID")
    require("Principal" not in rendered and "role/" not in rendered, "no principal or role ARN")


def normative_clauses(document: str) -> list[str]:
    """Split prose without allowing a negation to cross an adversative boundary."""
    units: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            units.append(" ".join(paragraph))
            paragraph.clear()

    structural = re.compile(r"^\s*(?:[-+*]\s+|\d+[.)]\s+|#{1,6}\s+|\|)")
    for line in document.splitlines():
        if not line.strip():
            flush_paragraph()
        elif structural.match(line):
            flush_paragraph()
            units.append(line)
        else:
            paragraph.append(line)
    flush_paragraph()

    separators = re.compile(
        r"(?:[;.!?]+\s+|\b(?:pero|sin embargo|"
        r"no obstante|aunque|but|however|nevertheless|although)\b)",
        re.IGNORECASE,
    )
    clauses: list[str] = []
    for unit in units:
        for clause in separators.split(unit):
            normalized = re.sub(r"[`>#]+", " ", clause)
            normalized = re.sub(r"^\s*(?:[-+*] |\d+[.)]\s*)", "", normalized)
            normalized = re.sub(r"\s+", " ", normalized).strip().lower()
            if normalized:
                clauses.append(normalized)
    return clauses


def negates(clause: str, predicate: str) -> bool:
    return re.search(
        rf"\b(?:no|not|nunca|never|sin|without)\b[^;.!?]*\b{predicate}", clause
    ) is not None


def validate_normative_claims(document: str) -> None:
    previous_non_eu_prohibition = False
    previous_catalog_denial = False
    for clause in normative_clauses(document):
        iam_predicate = r"(?:aplicad[oa]|adjuntad[oa]|desplegad[oa])"
        iam_assertion = re.search(
            r"(?:pol[ií]tica iam(?: ya)? (?:est[aá]|se encuentra|ha sido)? ?aplicada|"
            r"la pol[ií]tica se encuentra aplicada|iam (?:ya )?(?:est[aá]|ha sido) aplicado|"
            r"iam is applied|"
            r"permiso(?: ya)? (?:est[aá]|ha sido)? ?adjuntado al rol|"
            r"plantilla (?:ya )?est[aá] desplegada)",
            clause,
        )
        if iam_assertion and not negates(clause, iam_predicate):
            fail("contradictory IAM authorization")

        wildcard_subject = re.search(
            r"(?:resource\s*:?[ ]*[\"']?\*[\"']?|cualquier recurso|"
            r"wildcards? de recurso|bedrock:\*|invokemodel\*)",
            clause,
        )
        authorization = re.search(
            r"\b(?:permitid[oa]s?|autorizad[oa]s?|puede usarse|puede utilizarse|"
            r"podr[aá] invocar|queda autorizado|se permite)\b",
            clause,
        )
        if wildcard_subject and authorization and not negates(
            clause, r"(?:permitid[oa]s?|autorizad[oa]s?|usarse)"
        ):
            fail("contradictory wildcard authorization")

        streaming_subject = re.search(
            r"(?:invokemodelwithresponsestream|conversestream|streaming|"
            r"respuestas? en streaming)",
            clause,
        )
        if streaming_subject and authorization and not negates(
            clause, r"(?:permitid[oa]s?|autorizad[oa]s?|utilizarse|invocar)"
        ):
            fail("contradictory streaming authorization")

        if re.search(
            r"(?:(?:plantilla.*)?puede aplicarse directamente|"
            r"(?:plantilla.*)?puede desplegarse sin sustituci[oó]n|"
            r"no es necesaria revisi[oó]n humana|aprobaci[oó]n humana.*opcional|"
            r"do_not_apply.*puede ignorarse)",
            clause,
        ):
            fail("contradictory direct-apply authorization")

        if re.search(
            r"(?:listfoundationmodels|getfoundationmodel(?:availability)?|"
            r"disponibilidad del cat[aá]logo|consulta de solo lectura).*(?:confirma|"
            r"garantiza|prueba|demuestra).*(?:invokemodel funcionar[aá]|acceso efectivo|"
            r"cuenta puede invocar|autorizaci[oó]n runtime)",
            clause,
        ) and not negates(clause, r"(?:confirma|garantiza|prueba|demuestra)"):
            fail("contradictory catalog-access claim")
        catalog_confirmation = re.search(
            r"(?:confirma|garantiza|prueba|demuestra).*(?:invokemodel funcionar[aá]|"
            r"acceso efectivo|cuenta puede invocar|autorizaci[oó]n runtime)",
            clause,
        )
        if previous_catalog_denial and catalog_confirmation:
            fail("contradictory catalog-access claim")

        if re.search(
            r"(?:scp.*no afectan.*cross-region|puede omitirse.*regi[oó]n de destino|"
            r"no es necesario autorizar todos los destinos|regi[oó]n bloqueada no afecta|"
            r"regiones opt-in deben estar siempre habilitadas manualmente|"
            r"scp (?:was|has been) modified)",
            clause,
        ):
            fail("contradictory SCP or destination claim")

        non_eu = re.search(
            r"(?:perfil\s+(?:global|us|estadounidense|apac)|estados unidos|"
            r"asia[- ]pac[ií]fico|inferencia en estados unidos|\bglobal\b|"
            r"\bus\b|\bapac\b)",
            clause,
        )
        eu = re.search(
            r"(?:perfil\s+(?:ue|eu|europeo)|geograf[ií]a\s+(?:ue|eu)|"
            r"\b(?:ue|eu)\b)",
            clause,
        )
        non_eu_use = re.search(
            r"\b(?:permitid[oa]|autorizad[oa]|aprobada|puede utilizarse|puede usarse|"
            r"puede invocarse|se permite|podr[aá] usarse|podr[aá] utilizarse|"
            r"podr[aá] invocarse|queda autorizado|se autoriza su uso|fallback|"
            r"contingencia)\b",
            clause,
        )
        non_eu_negated = negates(
            clause, r"(?:permitid[oa]|autorizad[oa]|utilizarse|usarse)"
        ) or re.search(
            r"\b(?:no|sin)\b.*(?:global|\bus\b|apac|fallback)|"
            r"(?:global|\bus\b|apac).*\bprohibid[oa]\b",
            clause,
        )
        if non_eu and non_eu_use and not non_eu_negated:
            fail("non-EU profile authorization")
        if previous_non_eu_prohibition and non_eu_use and not non_eu and not eu:
            fail("non-EU profile authorization")

        previous_non_eu_prohibition = bool(
            non_eu
            and re.search(
                r"(?:prohibid[oa]s?|bloquead[oa]s?|no\s+(?:est[aá]\s+)?"
                r"(?:permitid[oa]s?|autorizad[oa]s?))",
                clause,
            )
        )
        previous_catalog_denial = bool(
            re.search(
                r"(?:listfoundationmodels|getfoundationmodel(?:availability)?|"
                r"disponibilidad del cat[aá]logo|consulta de solo lectura)",
                clause,
            )
            and re.search(r"\b(?:no|nunca)\b.*\b(?:garantiza|confirma|prueba|demuestra)", clause)
        )

        execution_patterns = (
            r"acceso de (?:la )?cuenta.*(?:est[aá]|queda) verificado",
            r"account access (?:is|has been) (?:verified|checked)",
            r"inferencia.*(?:est[aá]|queda) autorizada",
            r"inference (?:is|has been) authorized",
            r"pol[ií]tica runtime.*aprobada para ejecuci[oó]n",
            r"proyecto.*(?:est[aá]|queda) production-ready",
            r"the project (?:is|has been) production-ready",
            r"adr-013.*(?:est[aá]|queda|is) accepted",
            r"amazonbedrockfullaccess.*permitido para el runtime",
            r"amazonbedrockfullaccess (?:is required|required)",
        )
        for pattern in execution_patterns:
            if re.search(pattern, clause) and not negates(
                clause, r"(?:verificado|autorizada|aprobada|production-ready|accepted|permitido)"
            ):
                fail("contradictory execution authorization")


def validate_documents(root: Path) -> None:
    documents = {
        relative: strip_fences(read(root, relative))
        for relative in (DESIGN, COPILOT, BACKLOG, REVIEW, ADR)
    }
    design = documents[DESIGN]
    require("NO-GO PARA INFERENCIA BEDROCK REAL" in design, "documentation NO-GO")
    require("not production-ready" in design, "documentation not production-ready")
    require("ADR-013 remains **Proposed**" in design, "documentation ADR-013 Proposed")
    require(
        "bedrock-access-and-iam-design.md" in documents[COPILOT],
        "Copilot design link",
    )
    require("WA-031" in documents[BACKLOG], "backlog design control")
    require("WA-031" in documents[REVIEW], "review design control")
    require("- **Estado:** Proposed" in documents[ADR], "ADR-013 remains Proposed")
    validate_normative_claims("\n".join(documents.values()))


def run_guardrail(root: Path) -> None:
    root = root.resolve()
    validate_config(load_json(root, CONFIG))
    validate_policy(load_json(root, POLICY))
    validate_documents(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    run_guardrail(args.root)
    print("Bedrock access/IAM design controls passed.")


if __name__ == "__main__":
    main()
