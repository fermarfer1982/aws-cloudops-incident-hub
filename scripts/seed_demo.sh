#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8080}"

for file in demo-data/events/*.json; do
  echo "Enviando $file"
  curl --fail --silent --show-error \
    -X POST "$API_URL/events" \
    -H 'Content-Type: application/json' \
    --data-binary "@$file"
  echo
done
