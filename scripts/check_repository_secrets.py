#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "artifacts",
    "cdk.out",
    "node_modules",
}
MAX_FILE_SIZE = 2 * 1024 * 1024

PATTERNS = {
    "AWS access key identifier": re.compile(
        r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"
    ),
    "private key header": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "GitHub personal access token": re.compile(
        r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,255}(?![A-Za-z0-9])"
    ),
    "AWS secret access key assignment": re.compile(
        r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}"
    ),
}


def candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(ROOT).parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
        files.append(path)
    return sorted(files)


def main() -> None:
    findings: list[str] = []
    for path in candidate_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            for description, pattern in PATTERNS.items():
                if pattern.search(line):
                    relative = path.relative_to(ROOT)
                    findings.append(f"{relative}:{line_number}: {description}")

    if findings:
        details = "\n".join(findings)
        raise SystemExit(f"Potential secrets detected:\n{details}")

    print("Repository secret guardrail passed")


if __name__ == "__main__":
    main()
