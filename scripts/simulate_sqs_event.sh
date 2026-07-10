#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose exec -T backend python - <<'PY'
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from app.processor import handler

now = datetime.now(timezone.utc).isoformat()
event_id = uuid4().hex
message_id = f"local-{event_id[:12]}"
record = {
    "messageId": message_id,
    "body": json.dumps(
        {
            "version": "0",
            "id": event_id,
            "detail-type": "InfrastructureIncidentReceived",
            "source": "cloudops.incident-hub",
            "detail": {
                "event_id": event_id,
                "event": {
                    "source": "proxmox-lab-01",
                    "site": "Calahorra",
                    "type": "SERVICE_DOWN",
                    "message": "Simulación local del contrato EventBridge → SQS",
                    "timestamp": now,
                    "metadata": {"simulation": True},
                },
            },
        }
    ),
}

result = handler({"Records": [record]}, None)
print(json.dumps({"message_id": message_id, "result": result}, indent=2))
PY

printf '\nMétricas después de la simulación:\n'
curl -fsS http://localhost:8080/metrics | python3 -m json.tool
