from types import SimpleNamespace

from app import repository as repository_module
from app.repository import IncidentRepository


class UnexpectedResourceClient:
    def transact_write_items(self, **_kwargs):
        raise AssertionError(
            "The DynamoDB resource client must not execute low-level transactions"
        )


class FakeResource:
    def __init__(self):
        self.meta = SimpleNamespace(client=UnexpectedResourceClient())

    def Table(self, _name):
        return object()


class RecordingLowLevelClient:
    def __init__(self):
        self.calls = []

    def transact_write_items(self, **kwargs):
        self.calls.append(kwargs)


def test_transactions_use_a_low_level_dynamodb_client(monkeypatch):
    resource = FakeResource()
    low_level_client = RecordingLowLevelClient()

    monkeypatch.setattr(
        repository_module.boto3,
        "resource",
        lambda *_args, **_kwargs: resource,
    )
    monkeypatch.setattr(
        repository_module.boto3,
        "client",
        lambda *_args, **_kwargs: low_level_client,
    )

    repository = IncidentRepository()

    created = repository.put_if_absent(
        {
            "incident_id": "INC-20260710-TEST0001",
            "event_id": "test-event",
            "source": "test-source",
            "site": "Calahorra",
            "type": "BACKUP_FAILED",
            "message": "Transaction serialization regression test",
            "value": None,
            "metadata": {},
            "severity": "critical",
            "status": "open",
            "created_at": "2026-07-10T10:00:00+00:00",
            "updated_at": "2026-07-10T10:00:00+00:00",
        }
    )

    assert created is True
    assert len(low_level_client.calls) == 1

    transaction = low_level_client.calls[0]
    global_update = transaction["TransactItems"][1]["Update"]
    site_update = transaction["TransactItems"][2]["Update"]

    assert global_update["ExpressionAttributeValues"][":one"] == {"N": "1"}
    assert site_update["ExpressionAttributeValues"][":one"] == {"N": "1"}
