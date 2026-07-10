from __future__ import annotations

import pytest

from app.pagination import (
    InvalidContinuationToken,
    decode_continuation_token,
    encode_continuation_token,
)


def _create_incidents(client, count: int = 5) -> None:
    for index in range(count):
        response = client.post(
            "/events",
            json={
                "source": f"server-{index:02d}",
                "site": "Calahorra",
                "type": "SERVICE_RESTARTED",
                "message": f"Service restart number {index}",
            },
        )
        assert response.status_code == 201


def test_continuation_token_round_trip():
    context = {
        "index": "incidents-by-time",
        "severity": None,
        "status": None,
        "site": None,
    }
    key = {
        "incident_id": "INC-TEST",
        "entity_type": "INCIDENT",
        "created_at": "2026-07-10T10:00:00+00:00",
    }

    token = encode_continuation_token(key, context=context)

    assert token is not None
    assert decode_continuation_token(token, expected_context=context) == key


def test_continuation_token_rejects_different_filters():
    token = encode_continuation_token(
        {"offset": "2"},
        context={
            "index": "memory",
            "severity": None,
            "status": None,
            "site": "Calahorra",
        },
    )

    with pytest.raises(InvalidContinuationToken):
        decode_continuation_token(
            token or "",
            expected_context={
                "index": "memory",
                "severity": "critical",
                "status": None,
                "site": "Calahorra",
            },
        )


def test_events_endpoint_returns_non_overlapping_pages(client):
    _create_incidents(client)

    first = client.get("/events", params={"limit": 2})
    assert first.status_code == 200
    assert len(first.json()) == 2
    token = first.headers.get("x-next-token")
    assert token

    second = client.get("/events", params={"limit": 2, "next_token": token})
    assert second.status_code == 200
    assert len(second.json()) == 2

    first_ids = {item["incident_id"] for item in first.json()}
    second_ids = {item["incident_id"] for item in second.json()}
    assert first_ids.isdisjoint(second_ids)
    assert second.headers.get("x-next-token")


def test_events_endpoint_rejects_malformed_token(client):
    response = client.get("/events", params={"next_token": "not-a-valid-token"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid continuation token"}


def test_events_endpoint_rejects_token_reused_with_other_filters(client):
    _create_incidents(client, count=3)
    first = client.get("/events", params={"limit": 1, "site": "Calahorra"})
    token = first.headers["x-next-token"]

    response = client.get(
        "/events",
        params={
            "limit": 1,
            "site": "Calahorra",
            "severity": "warning",
            "next_token": token,
        },
    )

    assert response.status_code == 400
