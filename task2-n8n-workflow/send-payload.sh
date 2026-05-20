#!/usr/bin/env bash
# Sends a sample payload to the n8n webhook.
# Usage:
#   ./send-payload.sh sample-payloads/01-valid-high-acme.json
#   ./send-payload.sh sample-payloads/09-idempotency-replay.json 3
#
# Override the webhook URL with the WEBHOOK_URL env var.
set -euo pipefail

FILE="${1:?usage: send-payload.sh <payload.json> [repeat]}"
REPEAT="${2:-1}"
URL="${WEBHOOK_URL:-http://localhost:5678/webhook/lead-intake}"

if [[ ! -f "$FILE" ]]; then
  echo "payload file not found: $FILE" >&2
  exit 1
fi

for i in $(seq 1 "$REPEAT"); do
  echo
  echo "--- request $i/$REPEAT -> $URL ---"
  curl -sS -X POST "$URL" \
    -H "Content-Type: application/json" \
    --data @"$FILE"
  echo
done
