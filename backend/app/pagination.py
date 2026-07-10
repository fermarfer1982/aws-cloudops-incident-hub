from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from .repository import (
    INCIDENT_ENTITY_TYPE,
    INDEX_BY_SEVERITY,
    INDEX_BY_SITE,
    INDEX_BY_STATUS,
    INDEX_BY_TIME,
    IncidentRepository,
    _from_dynamodb,
)

TOKEN_VERSION = 1
MAX_CONTINUATION_TOKEN_LENGTH = 4096


class InvalidContinuationToken(ValueError):
    """Raised when a continuation token is malformed or used with other filters."""


@dataclass(frozen=True)
class IncidentPage:
    items: list[dict[str, Any]]
    next_token: str | None


def _token_context(
    *,
    index_name: str,
    severity: str | None,
    status: str | None,
    site: str | None,
) -> dict[str, Any]:
    return {
        "index": index_name,
        "severity": severity,
        "status": status,
        "site": site,
    }


def encode_continuation_token(
    last_evaluated_key: dict[str, Any] | None,
    *,
    context: dict[str, Any],
) -> str | None:
    if not last_evaluated_key:
        return None
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in last_evaluated_key.items()
    ):
        raise ValueError("DynamoDB continuation keys must contain only string attributes")

    payload = {
        "version": TOKEN_VERSION,
        "context": context,
        "key": last_evaluated_key,
    }
    raw = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_continuation_token(
    token: str,
    *,
    expected_context: dict[str, Any],
) -> dict[str, str]:
    if not token or len(token) > MAX_CONTINUATION_TOKEN_LENGTH:
        raise InvalidContinuationToken("Continuation token length is invalid")

    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.b64decode(
            (token + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise InvalidContinuationToken("Continuation token is malformed") from exc

    if not isinstance(payload, dict) or set(payload) != {"version", "context", "key"}:
        raise InvalidContinuationToken("Continuation token schema is invalid")
    if payload["version"] != TOKEN_VERSION:
        raise InvalidContinuationToken("Continuation token version is unsupported")
    if payload["context"] != expected_context:
        raise InvalidContinuationToken("Continuation token does not match the active filters")

    key = payload["key"]
    if not isinstance(key, dict) or not key:
        raise InvalidContinuationToken("Continuation token key is invalid")
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in key.items()):
        raise InvalidContinuationToken("Continuation token key attributes are invalid")
    return key


class PaginatedIncidentRepository(IncidentRepository):
    """Incident repository extension exposing bounded, cursor-based DynamoDB queries."""

    def list_page(
        self,
        *,
        limit: int = 100,
        severity: str | None = None,
        status: str | None = None,
        site: str | None = None,
        continuation_token: str | None = None,
    ) -> IncidentPage:
        if site:
            index_name = INDEX_BY_SITE
            partition_attribute = "site"
            partition_value = site
        elif status:
            index_name = INDEX_BY_STATUS
            partition_attribute = "status"
            partition_value = status
        elif severity:
            index_name = INDEX_BY_SEVERITY
            partition_attribute = "severity"
            partition_value = severity
        else:
            index_name = INDEX_BY_TIME
            partition_attribute = "entity_type"
            partition_value = INCIDENT_ENTITY_TYPE

        context = _token_context(
            index_name=index_name,
            severity=severity,
            status=status,
            site=site,
        )

        filters = []
        if severity and partition_attribute != "severity":
            filters.append(Attr("severity").eq(severity))
        if status and partition_attribute != "status":
            filters.append(Attr("status").eq(status))
        if site and partition_attribute != "site":
            filters.append(Attr("site").eq(site))

        filter_expression = None
        for expression in filters:
            filter_expression = expression if filter_expression is None else filter_expression & expression

        bounded_limit = min(max(limit, 1), 500)
        kwargs: dict[str, Any] = {
            "IndexName": index_name,
            "KeyConditionExpression": Key(partition_attribute).eq(partition_value),
            "ScanIndexForward": False,
            "Limit": bounded_limit,
        }
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression
        if continuation_token:
            kwargs["ExclusiveStartKey"] = decode_continuation_token(
                continuation_token,
                expected_context=context,
            )

        response = self._table.query(**kwargs)
        items = _from_dynamodb(response.get("Items", []))
        for item in items:
            item.pop("entity_type", None)

        last_evaluated_key = _from_dynamodb(response.get("LastEvaluatedKey"))
        next_token = encode_continuation_token(last_evaluated_key, context=context)
        return IncidentPage(items=items, next_token=next_token)
