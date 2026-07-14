from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.genai.evaluation import (
    CAUSE_NOT_ALLOWED,
    DATASET_INVALID,
    DUPLICATE_CASE_ID,
    DUPLICATE_PREDICTION_ID,
    EVIDENCE_NOT_ALLOWED,
    FORBIDDEN_CLAIM_PRESENT,
    PREDICTION_MISSING,
    PREDICTION_SCHEMA_INVALID,
    REQUIRED_MISSING_INFORMATION_ABSENT,
    EvaluationInputError,
    EvaluationSummary,
    evaluate_predictions,
    load_dataset,
    load_predictions,
    report_json,
)
from scripts.evaluate_ai_summary_predictions import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests/fixtures/ai_summary_evaluation_dataset.json"
PREDICTIONS = ROOT / "tests/fixtures/ai_summary_evaluation_predictions.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def load_positive():
    return load_dataset(DATASET), load_predictions(PREDICTIONS)


def one_case_inputs():
    cases, predictions = load_positive()
    return (cases[0],), (predictions[0],)


def finding_codes(report) -> list[str]:
    return [finding.code for result in report.results for finding in result.findings]


def test_versioned_dataset_and_predictions_are_valid_and_complete():
    cases, predictions = load_positive()
    assert len(cases) == 6
    assert {case.case_id for case in cases} == {
        "api-latency-001",
        "http-5xx-001",
        "lambda-timeout-001",
        "dynamodb-throttling-001",
        "insufficient-alarm-001",
        "executive-unconfirmed-001",
    }
    assert {prediction.case_id for prediction in predictions} == {
        case.case_id for case in cases
    }


def test_duplicate_dataset_case_id_is_rejected(tmp_path):
    raw = read_json(DATASET)
    raw.append(deepcopy(raw[0]))
    with pytest.raises(EvaluationInputError) as captured:
        load_dataset(write_json(tmp_path / "dataset.json", raw))
    assert captured.value.code == DUPLICATE_CASE_ID


@pytest.mark.parametrize(
    "mutation",
    [
        lambda case: case.update({"case_id": ""}),
        lambda case: case.update({"summary_type": "invalid"}),
        lambda case: case.update(
            {"allowed_evidence": [case["allowed_evidence"][0]] * 2}
        ),
        lambda case: case.update({"allowed_evidence": [""]}),
        lambda case: case.update({"unknown": True}),
        lambda case: case.update({"allowed_evidence": "not-a-list"}),
    ],
    ids=[
        "empty-case-id",
        "invalid-summary-type",
        "duplicate-list-item",
        "empty-list-item",
        "unknown-field",
        "wrong-type",
    ],
)
def test_invalid_dataset_cases_are_rejected(tmp_path, mutation):
    raw = read_json(DATASET)
    mutation(raw[0])
    with pytest.raises(EvaluationInputError) as captured:
        load_dataset(write_json(tmp_path / "dataset.json", raw))
    assert captured.value.code == DATASET_INVALID


@pytest.mark.parametrize("value", [{}, None, "list", []])
def test_dataset_top_level_must_be_a_non_empty_list(tmp_path, value):
    with pytest.raises(EvaluationInputError) as captured:
        load_dataset(write_json(tmp_path / "dataset.json", value))
    assert captured.value.code == DATASET_INVALID


def test_invalid_dataset_json_is_rejected_without_raw_payload(tmp_path):
    path = tmp_path / "dataset.json"
    path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(EvaluationInputError) as captured:
        load_dataset(path)
    assert captured.value.code == DATASET_INVALID
    assert "{invalid" not in str(captured.value)


def test_duplicate_prediction_id_is_rejected(tmp_path):
    raw = read_json(PREDICTIONS)
    raw.append(deepcopy(raw[0]))
    with pytest.raises(EvaluationInputError) as captured:
        load_predictions(write_json(tmp_path / "predictions.json", raw))
    assert captured.value.code == DUPLICATE_PREDICTION_ID


@pytest.mark.parametrize(
    "value",
    [None, {}, "list"],
)
def test_predictions_top_level_must_be_a_list(tmp_path, value):
    with pytest.raises(EvaluationInputError):
        load_predictions(write_json(tmp_path / "predictions.json", value))


def test_invalid_predictions_json_is_rejected(tmp_path):
    path = tmp_path / "predictions.json"
    path.write_text("[invalid", encoding="utf-8")
    with pytest.raises(EvaluationInputError):
        load_predictions(path)


def test_missing_prediction_is_reported():
    cases, predictions = one_case_inputs()
    report = evaluate_predictions(cases, ())
    assert report.failed_cases == 1
    assert finding_codes(report) == [PREDICTION_MISSING]


def test_unexpected_prediction_is_reported_without_adding_a_case():
    cases, predictions = one_case_inputs()
    unexpected = predictions[0].model_copy(update={"case_id": "unexpected-case"})
    report = evaluate_predictions(cases, predictions + (unexpected,))
    assert report.total_cases == 1
    assert report.unexpected_predictions == ("unexpected-case",)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"unknown": True}),
        lambda payload: payload.update({"summary": 42}),
        lambda payload: payload.update({"probable_causes": "invalid"}),
        lambda payload: payload["probable_causes"][0].update(
            {"confidence": "certain"}
        ),
        lambda payload: payload.pop("limitations"),
    ],
    ids=["unknown", "wrong-type", "wrong-structure", "invalid-enum", "incomplete"],
)
def test_prediction_schema_errors_are_sanitized(mutation):
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    mutation(raw)
    invalid = predictions[0].model_copy(update={"prediction": raw})
    report = evaluate_predictions(cases, (invalid,))
    assert finding_codes(report) == [PREDICTION_SCHEMA_INVALID]
    assert "Synthetic API" not in report_json(report)


def test_exact_evidence_is_allowed():
    cases, predictions = one_case_inputs()
    assert evaluate_predictions(cases, predictions).passed_cases == 1


@pytest.mark.parametrize(
    "evidence",
    [
        "Invented evidence",
        "Synthetic API latency exceeded",
        "API latency exceeded 2000 ms",
        "synthetic API latency exceeded 2000 ms",
    ],
    ids=["invented", "partial", "substring", "case-changed"],
)
def test_non_exact_evidence_is_rejected(evidence):
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    raw["probable_causes"][0]["supporting_evidence"] = [evidence]
    changed = predictions[0].model_copy(update={"prediction": raw})
    report = evaluate_predictions(cases, (changed,))
    assert finding_codes(report) == [EVIDENCE_NOT_ALLOWED]
    assert evidence not in report_json(report)


def test_two_exact_evidence_items_are_allowed():
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    raw["probable_causes"][0]["supporting_evidence"] = list(
        cases[0].allowed_evidence
    )
    changed = predictions[0].model_copy(update={"prediction": raw})
    report = evaluate_predictions(cases, (changed,))
    assert report.passed_cases == 1
    assert report.results[0].counts.supporting_evidence == 2


def test_valid_and_invalid_evidence_are_both_inspected():
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    raw["probable_causes"][0]["supporting_evidence"] = [
        cases[0].allowed_evidence[0],
        "Invented evidence",
    ]
    report = evaluate_predictions(
        cases, (predictions[0].model_copy(update={"prediction": raw}),)
    )
    assert finding_codes(report) == [EVIDENCE_NOT_ALLOWED]
    assert report.results[0].counts.supporting_evidence == 2


@pytest.mark.parametrize(
    "cause",
    ["Invented cause", "Application", "application saturation"],
    ids=["invented", "similar", "case-changed"],
)
def test_non_exact_causes_are_rejected(cause):
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    raw["probable_causes"][0]["description"] = cause
    report = evaluate_predictions(
        cases, (predictions[0].model_copy(update={"prediction": raw}),)
    )
    assert finding_codes(report) == [CAUSE_NOT_ALLOWED]


def test_multiple_allowed_causes_pass_and_mixed_causes_fail():
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    second = deepcopy(raw["probable_causes"][0])
    second["description"] = cases[0].allowed_probable_causes[1]
    raw["probable_causes"].append(second)
    valid = predictions[0].model_copy(update={"prediction": raw})
    assert evaluate_predictions(cases, (valid,)).passed_cases == 1
    raw["probable_causes"][1]["description"] = "Invented cause"
    mixed = predictions[0].model_copy(update={"prediction": raw})
    assert finding_codes(evaluate_predictions(cases, (mixed,))) == [CAUSE_NOT_ALLOWED]


def test_required_missing_information_is_exact_and_allows_additional_items():
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    raw["missing_information"].append("Additional synthetic information is absent")
    report = evaluate_predictions(
        cases, (predictions[0].model_copy(update={"prediction": raw}),)
    )
    assert report.passed_cases == 1


def test_absent_required_missing_information_is_reported():
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    raw["missing_information"] = []
    report = evaluate_predictions(
        cases, (predictions[0].model_copy(update={"prediction": raw}),)
    )
    assert finding_codes(report) == [REQUIRED_MISSING_INFORMATION_ABSENT]


def test_multiple_absent_required_items_are_each_reported():
    cases, predictions = one_case_inputs()
    case = cases[0].model_copy(
        update={"required_missing_information": ("Missing one", "Missing two")}
    )
    raw = deepcopy(predictions[0].prediction)
    raw["missing_information"] = []
    report = evaluate_predictions(
        (case,), (predictions[0].model_copy(update={"prediction": raw}),)
    )
    assert finding_codes(report) == [
        REQUIRED_MISSING_INFORMATION_ABSENT,
        REQUIRED_MISSING_INFORMATION_ABSENT,
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("summary", "Forbidden synthetic claim"),
        ("cause", "Forbidden synthetic claim"),
        ("recommended_actions", ["Review: Forbidden synthetic claim"]),
        ("missing_information", ["Unknown: Forbidden synthetic claim"]),
        ("limitations", ["Limit: Forbidden synthetic claim"]),
    ],
)
def test_forbidden_claim_is_detected_in_every_generated_field(field, value):
    cases, predictions = one_case_inputs()
    case = cases[0].model_copy(update={"forbidden_claims": ("Forbidden synthetic claim",)})
    raw = deepcopy(predictions[0].prediction)
    if field == "cause":
        raw["probable_causes"][0]["description"] = value
        case = case.model_copy(update={"allowed_probable_causes": (value,)})
    else:
        raw[field] = value
    if field == "missing_information":
        raw[field].append(case.required_missing_information[0])
    report = evaluate_predictions(
        (case,), (predictions[0].model_copy(update={"prediction": raw}),)
    )
    assert FORBIDDEN_CLAIM_PRESENT in finding_codes(report)
    assert "Forbidden synthetic claim" not in report_json(report)


def test_absence_of_forbidden_claims_passes():
    cases, predictions = one_case_inputs()
    assert FORBIDDEN_CLAIM_PRESENT not in finding_codes(
        evaluate_predictions(cases, predictions)
    )


def test_report_counts_invariants_order_and_determinism():
    cases, predictions = load_positive()
    report = evaluate_predictions(tuple(reversed(cases)), tuple(reversed(predictions)))
    serialized = report_json(report)
    assert report.total_cases == 6
    assert report.passed_cases + report.failed_cases == report.total_cases
    assert report.total_findings == sum(
        len(result.findings) for result in report.results
    )
    assert [result.case_id for result in report.results] == sorted(
        result.case_id for result in report.results
    )
    assert serialized == report_json(
        evaluate_predictions(tuple(reversed(cases)), tuple(reversed(predictions)))
    )


def test_summary_rejects_inconsistent_totals_and_boolean_integers():
    with pytest.raises(ValueError):
        EvaluationSummary(
            total_cases=2, passed_cases=1, failed_cases=0, total_findings=0
        )
    with pytest.raises(ValueError):
        EvaluationSummary(
            total_cases=True, passed_cases=1, failed_cases=0, total_findings=0
        )


def test_report_excludes_predictions_and_full_evidence():
    cases, predictions = one_case_inputs()
    raw = deepcopy(predictions[0].prediction)
    raw["probable_causes"][0]["supporting_evidence"] = [
        "Invented sensitive-looking evidence that must not be reported"
    ]
    report = evaluate_predictions(
        cases, (predictions[0].model_copy(update={"prediction": raw}),)
    )
    serialized = report_json(report)
    assert '"summary"' not in serialized
    assert "Invented sensitive-looking evidence" not in serialized
    assert raw["summary"] not in serialized


def test_cli_exit_zero_and_writes_deterministic_report(tmp_path, capsys):
    output = tmp_path / "report.json"
    args = ["--dataset", str(DATASET), "--predictions", str(PREDICTIONS), "--output", str(output)]
    assert cli_main(args) == 0
    first = output.read_text(encoding="utf-8")
    assert cli_main(args) == 0
    assert output.read_text(encoding="utf-8") == first
    assert json.loads(first)["passed_cases"] == 6
    console = capsys.readouterr().out
    assert "Result: PASS" in console
    assert "Synthetic API latency" not in console


def test_cli_exit_one_for_completed_evaluation_with_failures(tmp_path):
    raw = read_json(PREDICTIONS)
    raw.pop()
    predictions = write_json(tmp_path / "predictions.json", raw)
    output = tmp_path / "report.json"
    assert cli_main(
        ["--dataset", str(DATASET), "--predictions", str(predictions), "--output", str(output)]
    ) == 1


def test_cli_exit_two_for_invalid_input(tmp_path, capsys):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("invalid", encoding="utf-8")
    assert cli_main(
        ["--dataset", str(invalid), "--predictions", str(PREDICTIONS), "--output", str(tmp_path / "out.json")]
    ) == 2
    assert "invalid" not in capsys.readouterr().err.replace(str(invalid), "")


def test_cli_rejects_output_directory(tmp_path):
    assert cli_main(
        ["--dataset", str(DATASET), "--predictions", str(PREDICTIONS), "--output", str(tmp_path)]
    ) == 2


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as captured:
        cli_main(["--help"])
    assert captured.value.code == 0
    assert "--dataset" in capsys.readouterr().out


def test_evaluator_sources_do_not_import_network_or_aws_clients():
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "backend/app/genai/evaluation.py",
            "scripts/evaluate_ai_summary_predictions.py",
        )
    )
    for prohibited in ("boto3", "BedrockConverseClient", "FastAPI", "subprocess", "socket"):
        assert prohibited not in sources
