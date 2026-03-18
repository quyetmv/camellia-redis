#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
TENANT_A_PASS="${TENANT_A_PASS:-tenantApwd}"
TENANT_B_PASS="${TENANT_B_PASS:-tenantBpwd}"

KEY="lab:isolation:$(date +%s)"
VALUE_A="value_from_tenant_a"

redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" SET "$KEY" "$VALUE_A" >/dev/null
A_READ="$(redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" GET "$KEY")"
B_READ="$(redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_B_PASS" GET "$KEY")"

echo "key=$KEY"
echo "tenant_a_read=$A_READ"
echo "tenant_b_read=${B_READ:-<nil>}"

if [[ "$A_READ" != "$VALUE_A" ]]; then
  echo "[FAIL] Tenant A cannot read its own value"
  exit 1
fi

if [[ "$B_READ" == "$VALUE_A" ]]; then
  echo "[FAIL] Tenant isolation broken (tenant B saw tenant A value)"
  exit 1
fi

echo "[OK] Tenant isolation verified"
