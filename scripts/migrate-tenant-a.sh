#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:18080}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
TENANT_A_PASS="${TENANT_A_PASS:-tenantApwd}"

KEY="lab:migrate:$(date +%s)"

echo "[1/5] Write before migration via LB endpoint"
redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" SET "$KEY" "before_migrate" >/dev/null

echo "[2/5] Migrate tenant_a from pool_a to pool_b"
curl -sS -X POST "$CONTROL_PLANE_URL/tenants/tenant_a/migrate" \
  -H 'Content-Type: application/json' \
  -d '{"backend":"pool_b","tier":"shared-medium"}' | sed 's/^/[API] /'

echo "[3/5] Wait Camellia dynamic reload (about 2-4s)"
sleep 5

echo "[4/5] Read old key after migration (expect empty because now routing to pool_b)"
AFTER_READ="$(redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" GET "$KEY")"
echo "tenant_a_read_after_migration=${AFTER_READ:-<nil>}"

echo "[5/5] Write new value and verify on backend pool_b"
redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" SET "$KEY" "after_migrate" >/dev/null
POOL_A_VAL="$(redis-cli --raw -h 127.0.0.1 -p 63791 GET "$KEY")"
POOL_B_VAL="$(redis-cli --raw -h 127.0.0.1 -p 63792 GET "$KEY")"
echo "pool_a_value=${POOL_A_VAL:-<nil>}"
echo "pool_b_value=${POOL_B_VAL:-<nil>}"

echo "[OK] Tenant endpoint unchanged, backend moved by config"
