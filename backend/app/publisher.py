from __future__ import annotations

import json
from typing import Any

import boto3

from .config import settings
from .models import EventCreate


class EventPublishError(RuntimeError):
    pass


class EventPublisher:
    def __init__(
        self,
        *,
        client: Any | None = None,
        event_bus_name: str | None = None,
        source: str | None = None,
    ) -> None:
        self._client = client or boto3.client("events", region_name=settings.aws_region)
        self._event_bus_name = event_bus_name or settings.event_bus_name
        self._source = source or settings.event_source
        if not self._event_bus_name:
            raise ValueError("event_bus_name is required")

    def publish(self, event_id: str, event: EventCreate) -> None:
        detail = {
            "event_id": event_id,
            "event": event.model_dump(mode="json", exclude_none=True),
        }
        response = self._client.put_events(
            Entries=[
                {
                    "EventBusName": self._event_bus_name,
                    "Source": self._source,
                    "DetailType": "InfrastructureIncidentReceived",
                    "Detail": json.dumps(detail, separators=(",", ":")),
                }
            ]
        )
        if response.get("FailedEntryCount", 0):
            entries = response.get("Entries", [])
            error = entries[0] if entries else {"ErrorCode": "Unknown"}
            raise EventPublishError(
                f"EventBridge rejected the event: {error.get('ErrorCode', 'Unknown')}"
            )
