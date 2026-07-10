from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from botocore.exceptions import ClientError

from .classification import classify
from .models import EventCreate, IncidentStatus
from .repository import IncidentRepository


class IncidentNotFoundError(Exception):
    pass


class IncidentService:
    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.repository = repository or IncidentRepository()

    def create(self, event: EventCreate) -> dict:
        now = datetime.now(timezone.utc)
        timestamp = event.timestamp or now
        incident = {
            "incident_id": f"INC-{timestamp:%Y%m%d}-{uuid4().hex[:8].upper()}",
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
        self.repository.put(incident)
        return incident

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
