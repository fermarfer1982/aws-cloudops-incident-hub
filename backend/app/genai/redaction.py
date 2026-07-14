from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
)
TEXT_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(\bbearer\s+)[^\s,;]+"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)(\b(?:password|passwd|token)\s*=\s*)[^\s,;]+"),
)


def _sensitive_key(key: object) -> bool:
    normalized = str(key).lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in TEXT_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(lambda match: f"{match.group(1)}{REDACTED}", redacted)
        else:
            redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact_incident(value: Any, *, max_depth: int = 8, max_items: int = 100) -> Any:
    """Return a bounded redacted copy; this is an initial laboratory control, not PII detection."""

    def visit(item: Any, depth: int) -> Any:
        if depth > max_depth:
            return TRUNCATED
        if isinstance(item, dict):
            result: dict[Any, Any] = {}
            for index, (key, child) in enumerate(item.items()):
                if index >= max_items:
                    result[TRUNCATED] = TRUNCATED
                    break
                result[key] = REDACTED if _sensitive_key(key) else visit(child, depth + 1)
            return result
        if isinstance(item, list):
            values = [visit(child, depth + 1) for child in item[:max_items]]
            if len(item) > max_items:
                values.append(TRUNCATED)
            return values
        if isinstance(item, tuple):
            return [visit(child, depth + 1) for child in item[:max_items]]
        if isinstance(item, str):
            return redact_text(item)
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return redact_text(str(deepcopy(item)))

    return visit(value, 0)
