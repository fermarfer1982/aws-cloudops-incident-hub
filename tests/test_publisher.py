from __future__ import annotations

import json

import pytest

from app.models import EventCreate
from app.publisher import EventPublishError, EventPublisher


class FakeEventsClient:
    def __init__(self, response):
        self.response = response
        self.entries = []

    def put_events(self, *, Entries):
        self.entries.extend(Entries)
        return self.response


def test_publisher_builds_eventbridge_envelope():
    client = FakeEventsClient({"FailedEntryCount": 0, "Entries": [{"EventId": "1"}]})
    publisher = EventPublisher(
        client=client,
        event_bus_name="test-bus",
        source="cloudops.test",
    )
    event = EventCreate(
        source="srv-01",
        site="Calahorra",
        type="SERVICE_DOWN",
        message="Service unavailable",
    )

    publisher.publish("event-123", event)

    entry = client.entries[0]
    assert entry["EventBusName"] == "test-bus"
    assert entry["Source"] == "cloudops.test"
    detail = json.loads(entry["Detail"])
    assert detail["event_id"] == "event-123"
    assert detail["event"]["type"] == "SERVICE_DOWN"


def test_publisher_raises_when_eventbridge_rejects_entry():
    client = FakeEventsClient(
        {
            "FailedEntryCount": 1,
            "Entries": [{"ErrorCode": "InternalFailure"}],
        }
    )
    publisher = EventPublisher(client=client, event_bus_name="test-bus")
    event = EventCreate(
        source="srv-01",
        site="Calahorra",
        type="SERVICE_DOWN",
        message="Service unavailable",
    )

    with pytest.raises(EventPublishError):
        publisher.publish("event-123", event)
