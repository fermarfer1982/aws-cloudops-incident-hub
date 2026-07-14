from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

EVALUATOR_VERSION = "1.0"
DATASET_VERSION = "1.0"

PREDICTION_MISSING = "PREDICTION_MISSING"
PREDICTION_UNEXPECTED = "PREDICTION_UNEXPECTED"
PREDICTION_SCHEMA_INVALID = "PREDICTION_SCHEMA_INVALID"
EVIDENCE_NOT_ALLOWED = "EVIDENCE_NOT_ALLOWED"
CAUSE_NOT_ALLOWED = "CAUSE_NOT_ALLOWED"
REQUIRED_MISSING_INFORMATION_ABSENT = "REQUIRED_MISSING_INFORMATION_ABSENT"
FORBIDDEN_CLAIM_PRESENT = "FORBIDDEN_CLAIM_PRESENT"
DUPLICATE_CASE_ID = "DUPLICATE_CASE_ID"
DUPLICATE_PREDICTION_ID = "DUPLICATE_PREDICTION_ID"
DATASET_INVALID = "DATASET_INVALID"
PREDICTIONS_INVALID = "PREDICTIONS_INVALID"


class EvaluationInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    summary_type: Literal["technical", "executive"]
    allowed_evidence: tuple[str, ...] = Field(min_length=1, max_length=20)
    required_missing_information: tuple[str, ...] = Field(min_length=1, max_length=20)
    allowed_probable_causes: tuple[str, ...] = Field(min_length=1, max_length=20)
    forbidden_claims: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator(
        "allowed_evidence",
        "required_missing_information",
        "allowed_probable_causes",
        "forbidden_claims",
    )
    @classmethod
    def validate_unique_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(type(value) is not str or not value.strip() or len(value) > 500 for value in values):
            raise ValueError("list values must be unique, non-empty, bounded strings")
        if len(values) != len(set(values)):
            raise ValueError("list values must be unique, non-empty, bounded strings")
        return values

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case_id must be non-empty")
        return value


class EvaluationPrediction(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    prediction: dict[str, Any]

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case_id must be non-empty")
        return value


class PredictionCause(StrictModel):
    description: str = Field(min_length=1, max_length=500)
    confidence: Literal["low", "medium", "high"]
    supporting_evidence: tuple[str, ...] = Field(min_length=1, max_length=10)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must be non-empty")
        return value

    @field_validator("supporting_evidence")
    @classmethod
    def validate_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(type(value) is not str or not value.strip() or len(value) > 500 for value in values):
            raise ValueError("supporting evidence must be non-empty and bounded")
        return values


class PredictionPayload(StrictModel):
    summary: str = Field(min_length=1, max_length=2000)
    probable_causes: tuple[PredictionCause, ...] = Field(max_length=10)
    recommended_actions: tuple[str, ...] = Field(max_length=20)
    missing_information: tuple[str, ...] = Field(max_length=20)
    limitations: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("summary must be non-empty")
        return value

    @field_validator("recommended_actions", "missing_information", "limitations")
    @classmethod
    def validate_bounded_strings(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(type(value) is not str or not value.strip() or len(value) > 500 for value in values):
            raise ValueError("list values must be non-empty and bounded")
        return values


class EvaluationFinding(StrictModel):
    code: str
    field: str
    item_index: int | None = Field(default=None, ge=0, strict=True)
    message: str


class EvaluationCounts(StrictModel):
    probable_causes: int = Field(ge=0, strict=True)
    supporting_evidence: int = Field(ge=0, strict=True)
    recommended_actions: int = Field(ge=0, strict=True)
    missing_information: int = Field(ge=0, strict=True)
    limitations: int = Field(ge=0, strict=True)


class EvaluationCaseResult(StrictModel):
    case_id: str
    passed: bool
    findings: tuple[EvaluationFinding, ...]
    counts: EvaluationCounts


class EvaluationSummary(StrictModel):
    total_cases: int = Field(ge=0, strict=True)
    passed_cases: int = Field(ge=0, strict=True)
    failed_cases: int = Field(ge=0, strict=True)
    total_findings: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_case_totals(self) -> "EvaluationSummary":
        if self.passed_cases + self.failed_cases != self.total_cases:
            raise ValueError("passed_cases + failed_cases must equal total_cases")
        return self


class EvaluationReport(StrictModel):
    evaluator_version: str
    dataset_version: str
    total_cases: int = Field(ge=0, strict=True)
    passed_cases: int = Field(ge=0, strict=True)
    failed_cases: int = Field(ge=0, strict=True)
    total_findings: int = Field(ge=0, strict=True)
    findings_by_code: dict[str, int]
    unexpected_predictions: tuple[str, ...]
    results: tuple[EvaluationCaseResult, ...]

    @model_validator(mode="after")
    def validate_totals(self) -> "EvaluationReport":
        if self.passed_cases + self.failed_cases != self.total_cases:
            raise ValueError("passed_cases + failed_cases must equal total_cases")
        if len(self.results) != self.total_cases:
            raise ValueError("results length must equal total_cases")
        if sum(len(result.findings) for result in self.results) != self.total_findings:
            raise ValueError("total_findings must equal the findings in results")
        return self


def _read_json(path: Path, *, code: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(code, "Input file could not be read or validated") from exc


def load_dataset(path: Path) -> tuple[EvaluationCase, ...]:
    raw = _read_json(path, code=DATASET_INVALID)
    if not isinstance(raw, list) or not raw:
        raise EvaluationInputError(DATASET_INVALID, "Dataset must be a non-empty list")
    try:
        cases = tuple(EvaluationCase.model_validate(item) for item in raw)
    except (ValidationError, TypeError) as exc:
        raise EvaluationInputError(DATASET_INVALID, "Dataset schema is invalid") from exc
    identifiers = [case.case_id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise EvaluationInputError(DUPLICATE_CASE_ID, "Dataset case identifiers must be unique")
    return cases


def load_predictions(path: Path) -> tuple[EvaluationPrediction, ...]:
    raw = _read_json(path, code=PREDICTIONS_INVALID)
    if not isinstance(raw, list):
        raise EvaluationInputError(PREDICTIONS_INVALID, "Predictions must be a list")
    try:
        predictions = tuple(EvaluationPrediction.model_validate(item) for item in raw)
    except (ValidationError, TypeError) as exc:
        raise EvaluationInputError(PREDICTIONS_INVALID, "Predictions schema is invalid") from exc
    identifiers = [prediction.case_id for prediction in predictions]
    if len(identifiers) != len(set(identifiers)):
        raise EvaluationInputError(
            DUPLICATE_PREDICTION_ID, "Prediction case identifiers must be unique"
        )
    return predictions


def _finding(code: str, field: str, message: str, item_index: int | None = None) -> EvaluationFinding:
    return EvaluationFinding(code=code, field=field, item_index=item_index, message=message)


def _text_fields(payload: PredictionPayload) -> tuple[tuple[str, str, int | None], ...]:
    fields: list[tuple[str, str, int | None]] = [("summary", payload.summary, None)]
    fields.extend(
        ("probable_causes.description", cause.description, index)
        for index, cause in enumerate(payload.probable_causes)
    )
    for field, values in (
        ("recommended_actions", payload.recommended_actions),
        ("missing_information", payload.missing_information),
        ("limitations", payload.limitations),
    ):
        fields.extend((field, value, index) for index, value in enumerate(values))
    return tuple(fields)


def _evaluate_case(case: EvaluationCase, prediction: EvaluationPrediction | None) -> EvaluationCaseResult:
    findings: list[EvaluationFinding] = []
    empty_counts = EvaluationCounts(
        probable_causes=0,
        supporting_evidence=0,
        recommended_actions=0,
        missing_information=0,
        limitations=0,
    )
    if prediction is None:
        findings.append(_finding(PREDICTION_MISSING, "prediction", "Prediction is missing"))
        return EvaluationCaseResult(
            case_id=case.case_id, passed=False, findings=tuple(findings), counts=empty_counts
        )
    try:
        payload = PredictionPayload.model_validate(prediction.prediction)
    except ValidationError:
        findings.append(
            _finding(PREDICTION_SCHEMA_INVALID, "prediction", "Prediction schema is invalid")
        )
        return EvaluationCaseResult(
            case_id=case.case_id, passed=False, findings=tuple(findings), counts=empty_counts
        )

    allowed_evidence = set(case.allowed_evidence)
    allowed_causes = set(case.allowed_probable_causes)
    evidence_count = 0
    for cause_index, cause in enumerate(payload.probable_causes):
        if cause.description not in allowed_causes:
            findings.append(
                _finding(
                    CAUSE_NOT_ALLOWED,
                    "probable_causes.description",
                    "Probable cause is not explicitly allowed",
                    cause_index,
                )
            )
        for evidence_index, evidence in enumerate(cause.supporting_evidence):
            evidence_count += 1
            if evidence not in allowed_evidence:
                findings.append(
                    _finding(
                        EVIDENCE_NOT_ALLOWED,
                        f"probable_causes[{cause_index}].supporting_evidence",
                        "Supporting evidence is not explicitly allowed",
                        evidence_index,
                    )
                )

    provided_missing = set(payload.missing_information)
    for item_index, required in enumerate(case.required_missing_information):
        if required not in provided_missing:
            findings.append(
                _finding(
                    REQUIRED_MISSING_INFORMATION_ABSENT,
                    "missing_information",
                    "Required missing-information item is absent",
                    item_index,
                )
            )

    text_fields = _text_fields(payload)
    for claim_index, forbidden in enumerate(case.forbidden_claims):
        if any(forbidden in value for _, value, _ in text_fields):
            findings.append(
                _finding(
                    FORBIDDEN_CLAIM_PRESENT,
                    "generated_text",
                    "A forbidden claim is present",
                    claim_index,
                )
            )

    findings.sort(key=lambda item: (item.code, item.field, item.item_index or -1))
    counts = EvaluationCounts(
        probable_causes=len(payload.probable_causes),
        supporting_evidence=evidence_count,
        recommended_actions=len(payload.recommended_actions),
        missing_information=len(payload.missing_information),
        limitations=len(payload.limitations),
    )
    return EvaluationCaseResult(
        case_id=case.case_id,
        passed=not findings,
        findings=tuple(findings),
        counts=counts,
    )


def evaluate_predictions(
    cases: tuple[EvaluationCase, ...], predictions: tuple[EvaluationPrediction, ...]
) -> EvaluationReport:
    prediction_by_id = {prediction.case_id: prediction for prediction in predictions}
    case_ids = {case.case_id for case in cases}
    unexpected = tuple(sorted(set(prediction_by_id) - case_ids))
    results = tuple(
        _evaluate_case(case, prediction_by_id.get(case.case_id))
        for case in sorted(cases, key=lambda item: item.case_id)
    )
    passed = sum(result.passed for result in results)
    finding_counts = Counter(
        finding.code for result in results for finding in result.findings
    )
    total_findings = sum(finding_counts.values())
    return EvaluationReport(
        evaluator_version=EVALUATOR_VERSION,
        dataset_version=DATASET_VERSION,
        total_cases=len(results),
        passed_cases=passed,
        failed_cases=len(results) - passed,
        total_findings=total_findings,
        findings_by_code=dict(sorted(finding_counts.items())),
        unexpected_predictions=unexpected,
        results=results,
    )


def report_json(report: EvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
