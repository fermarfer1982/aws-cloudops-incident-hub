from __future__ import annotations

from datetime import datetime, timezone

from app.models import EventCreate
from app.service import IncidentService


def test_duplicate_event_id_is_idempotent(memory_repository):
    service = IncidentService(memory_repository)
    event = EventCreate(
        source="srv-01",
        site="Calahorra",
        type="SERVICE_DOWN",
        message="Service unavailable",
        timestamp=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
    )

    first = service.create(event, event_id="abcdef1234567890")
    second = service.create(event, event_id="abcdef1234567890")

    assert first["incident_id"] == second["incident_id"]
    assert len(memory_repository.items) == 1
