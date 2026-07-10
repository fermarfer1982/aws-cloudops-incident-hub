from __future__ import annotations

import json
import logging
from typing import Any

from .models import EventCreate
from .repository import IncidentRepository
from .service import IncidentService

logger = logging.getLogger(__name__)
repository = IncidentRepository()
service = IncidentService(repository)


def _extract_event(record: dict[str, Any]) -> tuple[str, EventCreate]:
    envelope = json.loads(record["body"])
    detail = envelope.get("detail", envelope)
    event_id = detail["event_id"]
    event = EventCreate.model_validate(detail["event"])
    return event_id, event


def handler(event: dict[str, Any], _context: Any) -> dict[str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")
        try:
            event_id, incident_event = _extract_event(record)
            incident = service.create(incident_event, event_id=event_id)
            logger.info(
                "Processed incident event_id=%s incident_id=%s",
                event_id,
                incident["incident_id"],
            )
        except Exception:
            logger.exception("Failed to process SQS message_id=%s", message_id)
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
