#!/usr/bin/env bash
set -euo pipefail
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:18080}"

curl -sS -X POST "$CONTROL_PLANE_URL/tenants/tenant_a/migrate" \
  -H 'Content-Type: application/json' \
  -d '{"backend":"pool_a","tier":"shared-small"}'
echo
