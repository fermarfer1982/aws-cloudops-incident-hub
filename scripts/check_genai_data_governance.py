#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

REQUIRED_HEADINGS = (
    "Estado y autoridad",
    "Alcance autorizado",
    "Finalidad",
    "Clasificación",
    "Allowlist exacta de atributos",
    "Datos prohibidos",
    "PII y secretos",
    "Minimización",
    "Región y transferencia",
    "Retención",
    "Borrado y cleanup",
    "Logging y telemetría",
    "Acceso humano y responsabilidad",
    "Auditoría",
    "Incidentes de datos",
    "Revisión de la política",
    "Cierre de WA-021",
)
ALLOWED_ATTRIBUTES = {"source", "site", "message", "value"}
CLASSIFICATION = {
    "Pública": "No necesaria",
    "Interna": "No",
    "Confidencial": "No",
    "Restringida": "No",
    "Sintética de laboratorio": "Sí",
}
REGION_PATTERN = re.compile(
    r"\b(?:af|ap|ca|eu|il|me|mx|sa|us)-"
    r"(?:central|east|north|northeast|northwest|south|southeast|southwest|west)-\d\b",
    re.IGNORECASE,
)
BEDROCK_ACTION = "bedrock:invokemodel"
IAM_GRANT_WORD = (
    r"(?:conced\w*|autoriz\w*|otorg\w*|habilit\w*|permit\w*|asign\w*|"
    r"añad\w*|agreg\w*|inclu\w*|recib\w*|obt\w*|dispon\w*|tendr\w*|"
    r"tien\w*|aplic\w*|solicit\w*|exist\w*)"
)
IAM_GRANT_PATTERN = re.compile(
    rf"\b{IAM_GRANT_WORD}\b",
    re.IGNORECASE,
)
IAM_NEGATIVE_SUBJECT = r"(?:ning[uú]n(?:[ao]s?)?|nadie)"
IAM_NEGATIVE_SUBJECT_PATTERN = re.compile(rf"\b{IAM_NEGATIVE_SUBJECT}\b", re.IGNORECASE)
IAM_POSITIVE_SUBJECT_RESET_PATTERN = re.compile(
    rf"(?:,|\b(?:y|o)\b)\s*(?:(?:otr[oa]s?|un(?:a|os|as)?|alg[uú]n(?:a|os|as)?|tod[oa]s?|"
    rf"el|la|los|las|cualquier)\b|se(?:\s+{IAM_GRANT_WORD})?\s*$)",
    re.IGNORECASE,
)
IAM_AMBIGUOUS_SUBJECT_PATTERN = re.compile(
    rf"\b{IAM_NEGATIVE_SUBJECT}\b[^.;\n|]*\b(?:salvo|excepto|a\s+menos\s+que)\b",
    re.IGNORECASE,
)
IAM_DOUBLE_NEGATION_PATTERN = re.compile(
    rf"(?:no\s+se\s+proh[ií]b\w*|no\s+est[aá]\s+prohibid\w*|"
    rf"no\s+se\s+descart\w*|nada\s+impid\w*)[^.;\n|]*"
    rf"(?:conced\w*|autoriz\w*|habilit\w*)|"
    rf"\b{IAM_NEGATIVE_SUBJECT}\b[^.;\n|]*\b(?:"
    rf"dej\w*\s+de|(?:est\w*\s+)?impedid\w*\s+de|"
    rf"(?:tien\w*\s+)?prohibid\w*(?:\s+de)?|impid\w*|"
    rf"proh[ií]b\w*|evit\w*|carec\w*\s+de|descart\w*)\b"
    rf"[^.;\n|]*(?:{IAM_GRANT_WORD}|{re.escape(BEDROCK_ACTION)})",
    re.IGNORECASE,
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


def strip_fenced_code_blocks(document: str) -> str:
    """Remove fenced examples while preserving their line structure."""
    sanitized: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    opening = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\r\n]*(?:\r\n|\r|\n)?$")

    for line in document.splitlines(keepends=True):
        line_ending_match = re.search(r"(?:\r\n|\r|\n)$", line)
        line_ending = line_ending_match.group(0) if line_ending_match else ""
        if fence_character is None:
            match = opening.fullmatch(line)
            if match:
                marker = match.group(1)
                fence_character = marker[0]
                fence_length = len(marker)
                sanitized.append(line_ending)
            else:
                sanitized.append(line)
            continue

        closing = re.compile(
            rf"^ {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*"
            rf"(?:\r\n|\r|\n)?$"
        )
        if closing.fullmatch(line):
            fence_character = None
            fence_length = 0
        sanitized.append(line_ending)

    require(fence_character is None, "unterminated fenced code block")
    return "".join(sanitized)


def split_normative_clauses(document: str) -> list[str]:
    """Split normative prose without splitting the Bedrock action identifier."""
    placeholder = "BEDROCK_INVOKE_MODEL_ACTION"
    protected = re.sub(re.escape(BEDROCK_ACTION), placeholder, document, flags=re.IGNORECASE)
    boundaries = re.compile(
        r"(?:\r?\n|[.;|]|(?<!`)\:(?!`)|"
        r"\b(?:pero|sin\s+embargo|no\s+obstante|aunque|en\s+cambio|"
        r"también|posteriormente|despu[eé]s)\b)",
        re.IGNORECASE,
    )
    return [
        clause.replace(placeholder, BEDROCK_ACTION).strip()
        for clause in boundaries.split(protected)
        if clause.strip()
    ]


def _grant_is_locally_negated(
    clause: str,
    match: re.Match[str],
    inherited_incomplete_negation: bool = False,
) -> bool:
    prefix = clause[: match.start()].rstrip()
    verbal_negation = (
        re.search(r"\b(?:no|nunca|ni)(?:\s+se)?\s*$", prefix, re.IGNORECASE) is not None
    )
    negative_subjects = list(IAM_NEGATIVE_SUBJECT_PATTERN.finditer(prefix))
    subject_negation = False
    if negative_subjects and IAM_AMBIGUOUS_SUBJECT_PATTERN.search(clause) is None:
        subject_scope = prefix[negative_subjects[-1].end() :]
        subject_negation = IAM_POSITIVE_SUBJECT_RESET_PATTERN.search(subject_scope) is None
    return (inherited_incomplete_negation and not prefix) or verbal_negation or subject_negation


def _coordinated_negative_assertion(clause: str) -> bool:
    action = re.escape(BEDROCK_ACTION)
    grant = IAM_GRANT_PATTERN.pattern
    normalized = re.sub(r"[`*_]", "", clause).strip()
    patterns = (
        rf"{action}\s+no\s+(?:se\s+)?{grant}"
        rf"(?:\s*,\s*{grant})*(?:\s+ni\s+(?:se\s+)?{grant})?",
        rf"no\s+(?:se\s+)?{grant}(?:\s+ni\s+(?:se\s+)?{grant})+\s+{action}",
    )
    return any(re.fullmatch(pattern, normalized, re.IGNORECASE) for pattern in patterns)


def validate_bedrock_iam_assertions(policy: str) -> None:
    action_context = False
    incomplete_negation = False
    for clause in split_normative_clauses(policy):
        lower = clause.lower()
        contains_action = BEDROCK_ACTION in lower
        applies_to_action = contains_action or action_context
        grants: list[re.Match[str]] = []
        if applies_to_action:
            require(
                IAM_DOUBLE_NEGATION_PATTERN.search(clause) is None,
                "Bedrock IAM contradiction",
            )
            grants = list(IAM_GRANT_PATTERN.finditer(clause))
            if grants and not _coordinated_negative_assertion(clause):
                require(
                    all(
                        _grant_is_locally_negated(clause, match, incomplete_negation)
                        for match in grants
                    ),
                    "Bedrock IAM contradiction",
                )
        incomplete_negation = contains_action and re.search(
            r"\b(?:no|no\s+se)\s*$", clause, re.IGNORECASE
        ) is not None
        action_context = contains_action or (applies_to_action and bool(grants))


def parse_sections(document: str) -> dict[str, str]:
    lines = document.splitlines()
    require(lines and lines[0].strip() == "# Gobierno de datos para GenAI", "policy title")
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[1:]:
        match = re.fullmatch(r"##\s+(.+?)\s*", line)
        if match:
            heading = match.group(1)
            require(heading not in sections, f"duplicate heading {heading}")
            sections[heading] = []
            current = heading
            continue
        if current is not None:
            sections[current].append(line)
    for heading in REQUIRED_HEADINGS:
        require(heading in sections, f"missing heading ## {heading}")
        require(any(line.strip() for line in sections[heading]), f"empty section {heading}")
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def parse_table(section: str, headers: tuple[str, ...], control: str) -> list[dict[str, str]]:
    lines = section.splitlines()
    starts = [index for index, line in enumerate(lines) if _cells(line) == list(headers)]
    require(len(starts) == 1, control)
    start = starts[0]
    require(start + 1 < len(lines), control)
    separator = _cells(lines[start + 1])
    require(
        separator is not None
        and len(separator) == len(headers)
        and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator),
        control,
    )
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for line in lines[start + 2 :]:
        cells = _cells(line)
        if cells is None:
            if rows:
                break
            continue
        require(len(cells) == len(headers), control)
        row = tuple(cells)
        require(row not in seen, control)
        seen.add(row)
        rows.append(dict(zip(headers, cells, strict=True)))
    require(rows, control)
    table_lines = sum(1 for line in lines if _cells(line) == list(headers))
    require(table_lines == 1, control)
    return rows


def _contains_all(text: str, phrases: tuple[str, ...], control: str) -> None:
    lowered = re.sub(r"\s+", " ", text.lower())
    require(all(phrase.lower() in lowered for phrase in phrases), control)


def validate_classification(section: str) -> None:
    rows = parse_table(
        section,
        ("Clase", "Definición", "Permitida en primera prueba"),
        "classification table semantics",
    )
    require(len(rows) == 5, "classification table semantics")
    actual: dict[str, str] = {}
    for row in rows:
        name = row["Clase"]
        require(name not in actual and row["Definición"], "classification table semantics")
        actual[name] = row["Permitida en primera prueba"]
    require(actual == CLASSIFICATION, "classification table semantics")
    require(
        "La única clasificación admitida es **Sintética de laboratorio**" in section,
        "classification table semantics",
    )


def validate_allowlist(section: str) -> None:
    rows = parse_table(
        section,
        ("Atributo", "Tipo permitido", "Restricción"),
        "allowlist table structure",
    )
    require(len(rows) == 4, "allowlist cardinality")
    by_name: dict[str, dict[str, str]] = {}
    for row in rows:
        match = re.fullmatch(r"`([^`]+)`", row["Atributo"])
        require(match is not None, "exact attribute allowlist")
        name = match.group(1)
        require(name not in by_name, "exact attribute allowlist")
        by_name[name] = row
    require(set(by_name) == ALLOWED_ATTRIBUTES, "exact attribute allowlist")
    expected_types = {
        "source": "string",
        "site": "string",
        "message": "string",
        "value": "number o null",
    }
    require(
        all(by_name[name]["Tipo permitido"] == expected for name, expected in expected_types.items()),
        "allowlist type semantics",
    )
    restrictions = {
        "source": ("valor sintético fijo", "allowlist versionada"),
        "site": ("etiqueta sintética", "nunca una sede real"),
        "message": ("texto fijo de la fixture sintética", "sin entrada libre"),
        "value": ("valor sintético acotado", "nunca texto"),
    }
    for name, phrases in restrictions.items():
        _contains_all(by_name[name]["Restricción"], phrases, "allowlist restriction semantics")
    _contains_all(
        section,
        (
            "Ningún atributo adicional puede enviarse",
            "clasificación desconocida implica rechazo",
            "incident_id",
            "no debe enviarse al modelo ni incluirse en la evidencia",
            "Cambiar esta allowlist requiere una nueva PR de gobierno",
        ),
        "allowlist normative semantics",
    )


def validate_retention(section: str) -> None:
    rows = parse_table(
        section,
        ("Elemento", "Persistencia permitida", "Retención"),
        "retention table semantics",
    )
    by_element = {row["Elemento"]: row for row in rows}
    require(len(by_element) == len(rows) == 9, "retention table semantics")
    expected = {
        "Prompt y contexto construidos": ("No", "Memoria durante la invocación"),
        "Respuesta bruta": ("No", "Memoria hasta validación y revisión autorizada"),
        "Texto generado": ("No", "No logs, no artifacts, no Git"),
        "Temporales de GitHub Actions": ("Solo durante el job", "Eliminación bajo `always()`"),
        "Artifact técnico": ("Solo evidencia saneada", "Máximo 7 días"),
        "Archivos en `mirofish`": ("No", "Deben quedar ausentes"),
    }
    for element, values in expected.items():
        require(element in by_element, "retention table semantics")
        require(
            (by_element[element]["Persistencia permitida"], by_element[element]["Retención"])
            == values,
            "retention table semantics",
        )


def validate_incident_response(section: str) -> None:
    items: list[tuple[int, str]] = []
    current: tuple[int, list[str]] | None = None
    for line in section.splitlines():
        match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if match:
            if current:
                items.append((current[0], " ".join(current[1])))
            current = (int(match.group(1)), [match.group(2)])
        elif current and line.strip():
            current[1].append(line.strip())
    if current:
        items.append((current[0], " ".join(current[1])))
    require([number for number, _ in items] == list(range(1, 9)), "incident response semantics")
    required = (
        ("bloquear la inferencia", "detener el workflow"),
        ("evitar imprimir el contenido",),
        ("eliminar temporales",),
        ("ejecutar destroy",),
        ("verificar ausencia",),
        ("únicamente un estado saneado",),
        ("no reintentar",),
        ("revisión de seguridad", "antes de otra ejecución"),
    )
    for (_, item), phrases in zip(items, required, strict=True):
        _contains_all(item, phrases, "incident response semantics")


def validate_material_sections(sections: dict[str, str]) -> None:
    requirements = {
        "Estado y autoridad": (
            "al fusionarse esta política",
            "una sola persona",
            "no constituye aprobación jurídica",
            "aprobación organizativa independiente",
        ),
        "Alcance autorizado": (
            "un solo incidente",
            "completamente sintético",
            "fixture versionada",
            "una sola invocación",
            "no autorizan ejecutar la inferencia",
        ),
        "Finalidad": (
            "resumen consultivo",
            "decisiones automáticas",
            "entrenamiento",
            "rag",
            "caching",
        ),
        "Datos prohibidos": (
            "datos empresariales",
            "datos personales",
            "credenciales",
            "clasificación desconocida",
        ),
        "PII y secretos": (
            "redacción actual no constituye detección suficiente de pii",
            "falla de forma cerrada",
            "el valor detectado nunca se registra",
        ),
        "Minimización": (
            "source`, `site`, `message` y `value",
            "no se envía el objeto completo de dynamodb",
            "no existe fallback",
        ),
        "Región y transferencia": (
            "no aprueba todavía ninguna región ni modelo",
            "cross-region inference queda prohibida",
            "verificará oficialmente",
        ),
        "Borrado y cleanup": (
            "tanto en éxito como en fallo",
            "ejecutará de forma incondicional",
            "ausencia del stack, la lambda y el log group",
        ),
        "Logging y telemetría": (
            "solo se permiten versión de prompt",
            "se prohíben prompt",
            "respuesta bruta",
            "datos personales o empresariales",
        ),
        "Acceso humano y responsabilidad": (
            "evaluar todas las afirmaciones",
            "la salida es consultiva",
            "deberá definirse antes de la prueba",
        ),
        "Cierre de WA-021": (
            "al fusionarse esta política",
            "caso sintético de laboratorio",
            "no autoriza inferencia ni datos reales",
            "no aprueba región o modelo",
            "not production-ready",
        ),
    }
    for heading, phrases in requirements.items():
        _contains_all(sections[heading], phrases, f"section semantics {heading}")


def validate_contradictions(policy: str) -> None:
    compact = re.sub(r"\s+", " ", policy)
    lower = compact.lower()
    require(REGION_PATTERN.search(policy) is None, "region approval contradiction")
    for pattern in (
        r"(?:el\s+)?modelo\s+[^.]{0,80}(?:queda|está|es)\s+aprobado",
        r"se\s+aprueba\s+(?:el\s+)?modelo",
        r"inference\s+profile\s+[^.]{0,80}aprobado",
        r"modelo\s+seleccionado\s*:",
    ):
        require(re.search(pattern, lower) is None, "model approval contradiction")
    validate_bedrock_iam_assertions(policy)
    for match in re.finditer(r"production-ready", lower):
        prefix = lower[max(0, match.start() - 30) : match.start()]
        require("not " in prefix or "no está " in prefix, "production readiness contradiction")
    forbidden = (
        r"datos\s+(?:internos|reales|empresariales)\s+(?:están\s+)?permitidos",
        r"se\s+autorizan\s+datos\s+(?:internos|reales|empresariales)",
        r"clase\s+interna\s+(?:está\s+)?permitida",
        r"(?<!no\s)autoriza\s+(?:ejecutar\s+)?(?:la\s+)?inferencia",
        r"reintentar\s+automáticamente",
        r"(?:prompt|contexto|respuesta\s+bruta|texto\s+generado)[^.]{0,80}(?:se\s+persiste|puede\s+persistir|persistencia\s+permitida\s*:\s*sí)",
    )
    require(not any(re.search(pattern, lower) for pattern in forbidden), "NO-GO contradiction")


def validate_repository_status(readme: str, backlog: str, review: str, release: str) -> None:
    expected = (
        "WA-021: clasificación y retención completadas para el laboratorio sintético; "
        "datos reales, privacidad organizativa y producción permanecen pendientes."
    )
    require(expected in readme, "WA-021 repository status consistency")
    require(
        "Completado para el alcance sintético de laboratorio" in backlog
        and "Datos reales, región, modelo, IAM Bedrock e inferencia continúan prohibidos" in backlog,
        "WA-021 repository status consistency",
    )
    require(
        "WA-021 is closed only as a policy for a future single-inference test with synthetic laboratory data"
        in review,
        "WA-021 repository status consistency",
    )
    require(
        "WA-021: clasificación y retención cerradas para el laboratorio sintético; "
        "datos reales, requisitos organizativos de privacidad y uso en producción "
        "permanecen pendientes."
        in release,
        "WA-021 repository status consistency",
    )


def run_guardrail(root: Path) -> None:
    def normative(relative: str, control: str) -> str:
        return strip_fenced_code_blocks(_read(root / relative, control))

    policy = normative("docs/genai-data-governance.md", "missing policy")
    backlog = normative("docs/well-architected-backlog.md", "missing backlog")
    review = normative("docs/well-architected-review.md", "missing review")
    design = normative("docs/bedrock-incident-copilot.md", "missing design")
    adr = normative("docs/adr/013-amazon-bedrock-incident-copilot.md", "missing ADR-013")
    readme = normative("README.md", "missing README")
    release = normative("docs/v1.0.0-lab-release-and-rollback.md", "missing release runbook")
    sections = parse_sections(policy)
    validate_material_sections(sections)
    validate_classification(sections["Clasificación"])
    validate_allowlist(sections["Allowlist exacta de atributos"])
    validate_retention(sections["Retención"])
    validate_incident_response(sections["Incidentes de datos"])
    validate_contradictions(policy)
    require("- **Estado:** Proposed" in adr, "ADR-013 remains Proposed")
    link = "[política de gobierno de datos GenAI](genai-data-governance.md)"
    require(link in review, "review policy link")
    require(link in design, "design policy link")
    require("**Production readiness:** Not production-ready" in review, "project not production-ready")
    require("not production-ready" in design.lower(), "design not production-ready")
    validate_repository_status(readme, backlog, review, release)


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
