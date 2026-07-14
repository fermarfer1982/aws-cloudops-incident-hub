#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.genai.evaluation import (  # noqa: E402
    EvaluationInputError,
    evaluate_predictions,
    load_dataset,
    load_predictions,
    report_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate saved synthetic AI-summary predictions locally."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _write_report(path: Path, content: str) -> None:
    if path.exists() and path.is_dir():
        raise OSError("Output path is a directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cases = load_dataset(args.dataset)
        predictions = load_predictions(args.predictions)
        report = evaluate_predictions(cases, predictions)
        _write_report(args.output, report_json(report))
    except (EvaluationInputError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Dataset: {args.dataset}")
    print(f"Cases: {report.total_cases}")
    print(f"Passed: {report.passed_cases}")
    print(f"Failed: {report.failed_cases}")
    print(f"Findings: {report.total_findings}")
    print(f"Report: {args.output}")
    passed = report.failed_cases == 0 and not report.unexpected_predictions
    print("Result: PASS" if passed else "Result: FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
