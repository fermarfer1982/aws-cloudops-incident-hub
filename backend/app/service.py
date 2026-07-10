from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from botocore.exceptions import ClientError

from .classification import classify
from .models import EventCreate, IncidentStatus
from .publisher import EventPublisher
from .repository import IncidentRepository


class IncidentNotFoundError(Exception):
    pass


class IncidentService:
    def __init__(
        self,
        repository: IncidentRepository | None = None,
        publisher: EventPublisher | None = None,
    ) -> None:
        self.repository = repository or IncidentRepository()
        self.publisher = publisher

    @staticmethod
    def _incident_id(event_id: str, timestamp: datetime) -> str:
        return f"INC-{timestamp:%Y%m%d}-{event_id[:8].upper()}"

    def ingest(self, event: EventCreate) -> dict:
        received_at = datetime.now(timezone.utc)
        normalized_event = event.model_copy(
            update={"timestamp": event.timestamp or received_at}
        )
        event_id = uuid4().hex
        incident_id = self._incident_id(event_id, normalized_event.timestamp)

        if self.publisher is not None:
            self.publisher.publish(event_id, normalized_event)
            return {
                "event_id": event_id,
                "incident_id": incident_id,
                "status": "accepted",
                "mode": "asynchronous",
                "received_at": received_at.isoformat(),
            }

        return self.create(normalized_event, event_id=event_id)

    def create(self, event: EventCreate, *, event_id: str | None = None) -> dict:
        now = datetime.now(timezone.utc)
        timestamp = event.timestamp or now
        normalized_event_id = event_id or uuid4().hex
        incident_id = self._incident_id(normalized_event_id, timestamp)
        incident = {
            "incident_id": incident_id,
            "event_id": normalized_event_id,
            "source": event.source,
            "site": event.site,
            "type": event.type,
            "message": event.message,
            "value": event.value,
            "metadata": event.metadata,
            "severity": classify(event).value,
            "status": IncidentStatus.OPEN.value,
            "created_at": timestamp.isoformat(),
            "updated_at": now.isoformat(),
        }

        if self.repository.put_if_absent(incident):
            return incident

        existing = self.repository.get(incident_id)
        if existing is None:
            raise RuntimeError("Idempotent write failed but the incident was not found")
        return existing

    def update_status(self, incident_id: str, status: IncidentStatus) -> dict:
        try:
            return self.repository.update_status(
                incident_id,
                status.value,
                datetime.now(timezone.utc).isoformat(),
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise IncidentNotFoundError(incident_id) from exc
            raise

    def metrics(self) -> dict:
        incidents = self.repository.list(limit=500)
        status_counts = Counter(item["status"] for item in incidents)
        severity_counts = Counter(item["severity"] for item in incidents)
        site_counts = Counter(item["site"] for item in incidents)
        return {
            "total": len(incidents),
            "open": status_counts["open"],
            "investigating": status_counts["investigating"],
            "resolved": status_counts["resolved"],
            "critical": severity_counts["critical"],
            "warning": severity_counts["warning"],
            "info": severity_counts["info"],
            "by_site": dict(site_counts.most_common()),
        }
