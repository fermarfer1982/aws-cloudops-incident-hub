from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_service
from app.service import IncidentService


class MemoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}

    def put_if_absent(self, incident: dict) -> bool:
        incident_id = incident["incident_id"]
        if incident_id in self.items:
            return False
        self.items[incident_id] = incident
        return True

    def get(self, incident_id: str) -> dict | None:
        return self.items.get(incident_id)

    def update_status(self, incident_id: str, status: str, updated_at: str) -> dict:
        if incident_id not in self.items:
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "not found"}},
                "UpdateItem",
            )
        self.items[incident_id]["status"] = status
        self.items[incident_id]["updated_at"] = updated_at
        return self.items[incident_id]

    def list(self, *, limit=100, severity=None, status=None, site=None):
        items = list(self.items.values())
        if severity:
            items = [item for item in items if item["severity"] == severity]
        if status:
            items = [item for item in items if item["status"] == status]
        if site:
            items = [item for item in items if item["site"] == site]
        return sorted(items, key=lambda item: item["created_at"], reverse=True)[:limit]


@pytest.fixture
def memory_repository() -> MemoryRepository:
    return MemoryRepository()


@pytest.fixture
def client(memory_repository: MemoryRepository) -> Iterator[TestClient]:
    service = IncidentService(memory_repository)
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def app_client_factory(memory_repository: MemoryRepository):
    clients: list[TestClient] = []

    def factory(*, publisher=None):
        service = IncidentService(memory_repository, publisher=publisher)
        app.dependency_overrides[get_service] = lambda: service
        test_client = TestClient(app)
        test_client.__enter__()
        clients.append(test_client)
        return test_client, memory_repository

    yield factory

    for test_client in clients:
        test_client.__exit__(None, None, None)
    app.dependency_overrides.clear()
