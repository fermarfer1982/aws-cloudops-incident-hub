from __future__ import annotations

import json

from app import processor


def test_processor_creates_incident_and_returns_no_failures(monkeypatch):
    calls = []

    class FakeService:
        def create(self, event, *, event_id=None):
            calls.append((event_id, event))
            return {"incident_id": "INC-20260710-ABCDEF12"}

    monkeypatch.setattr(processor, "service", FakeService())
    event = {
        "Records": [
            {
                "messageId": "message-1",
                "body": json.dumps(
                    {
                        "detail": {
                            "event_id": "abcdef1234567890",
                            "event": {
                                "source": "pbs-01",
                                "site": "Calahorra",
                                "type": "BACKUP_FAILED",
                                "message": "Backup failed",
                                "timestamp": "2026-07-10T10:00:00Z",
                            },
                        }
                    }
                ),
            }
        ]
    }

    result = processor.handler(event, None)

    assert result == {"batchItemFailures": []}
    assert calls[0][0] == "abcdef1234567890"
    assert calls[0][1].type == "BACKUP_FAILED"


def test_processor_reports_only_malformed_message_as_failed(monkeypatch):
    class FakeService:
        def create(self, event, *, event_id=None):
            return {"incident_id": "INC-OK"}

    monkeypatch.setattr(processor, "service", FakeService())
    event = {
        "Records": [
            {"messageId": "bad-message", "body": "not-json"},
            {
                "messageId": "good-message",
                "body": json.dumps(
                    {
                        "detail": {
                            "event_id": "12345678",
                            "event": {
                                "source": "srv-01",
                                "site": "Madrid",
                                "type": "SERVICE_DOWN",
                                "message": "Service unavailable",
                            },
                        }
                    }
                ),
            },
        ]
    }

    result = processor.handler(event, None)

    assert result == {
        "batchItemFailures": [{"itemIdentifier": "bad-message"}]
    }
