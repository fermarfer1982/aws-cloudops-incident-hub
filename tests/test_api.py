def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ingestion_mode"] == "synchronous-local"


def test_create_classifies_backup_failure_as_critical(client):
    response = client.post(
        "/events",
        json={
            "source": "pbs-01",
            "site": "Calahorra",
            "type": "BACKUP_FAILED",
            "message": "Nightly backup failed",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["severity"] == "critical"
    assert body["status"] == "open"
    assert body["incident_id"].startswith("INC-")
    assert body["event_id"]


def test_disk_above_95_is_critical(client):
    response = client.post(
        "/events",
        json={
            "source": "proxmox-01",
            "site": "Calahorra",
            "type": "DISK_USAGE_HIGH",
            "message": "Disk threshold exceeded",
            "value": 96.2,
        },
    )
    assert response.json()["severity"] == "critical"


def test_list_filters_by_site(client):
    for site in ("Calahorra", "Almeria"):
        client.post(
            "/events",
            json={
                "source": "server-01",
                "site": site,
                "type": "SERVICE_RESTARTED",
                "message": "Service restarted successfully",
            },
        )

    response = client.get("/events", params={"site": "Almeria"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["site"] == "Almeria"


def test_update_status_and_metrics(client):
    created = client.post(
        "/events",
        json={
            "source": "fw-01",
            "site": "Madrid",
            "type": "SECURITY_ALERT",
            "message": "Repeated authentication failures",
        },
    ).json()

    updated = client.patch(
        f"/events/{created['incident_id']}/status",
        json={"status": "investigating"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "investigating"

    metrics = client.get("/metrics").json()
    assert metrics["total"] == 1
    assert metrics["critical"] == 1
    assert metrics["investigating"] == 1


def test_asynchronous_ingestion_returns_accepted(app_client_factory):
    class FakePublisher:
        def __init__(self):
            self.calls = []

        def publish(self, event_id, event):
            self.calls.append((event_id, event))

    publisher = FakePublisher()
    client, repository = app_client_factory(publisher=publisher)

    response = client.post(
        "/events",
        json={
            "source": "srv-01",
            "site": "Calahorra",
            "type": "SERVICE_DOWN",
            "message": "Service unavailable",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["mode"] == "asynchronous"
    assert body["incident_id"].startswith("INC-")
    assert len(publisher.calls) == 1
    assert repository.items == {}
