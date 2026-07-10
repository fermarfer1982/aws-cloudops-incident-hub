#!/usr/bin/env bash
set -euo pipefail
API_URL="${API_URL:-http://localhost:8080}"

curl --fail --silent "$API_URL/health" | python -m json.tool
curl --fail --silent -X POST "$API_URL/events" \
  -H 'Content-Type: application/json' \
  --data-binary @demo-data/events/backup-failed.json | python -m json.tool
curl --fail --silent "$API_URL/metrics" | python -m json.tool
