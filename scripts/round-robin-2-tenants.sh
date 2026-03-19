#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
TENANT_A_PASS="${TENANT_A_PASS:-tenantApwd}"
TENANT_B_PASS="${TENANT_B_PASS:-tenantBpwd}"
ROUNDS="${ROUNDS:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0}"

if [[ "$ROUNDS" -le 0 ]]; then
  echo "[FAIL] ROUNDS must be > 0"
  exit 1
fi

KEY="${KEY:-lab:round_robin:$(date +%s)}"
LAST_A=""
LAST_B=""

echo "[INFO] host=$REDIS_HOST port=$REDIS_PORT rounds=$ROUNDS key=$KEY"

# cleanup for deterministic run
redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" DEL "$KEY" >/dev/null
redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_B_PASS" DEL "$KEY" >/dev/null

for ((i = 1; i <= ROUNDS; i++)); do
  if (( i % 2 == 1 )); then
    tenant="A"
    pass="$TENANT_A_PASS"
    value="A_$i"
    LAST_A="$value"
  else
    tenant="B"
    pass="$TENANT_B_PASS"
    value="B_$i"
    LAST_B="$value"
  fi

  redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$pass" SET "$KEY" "$value" >/dev/null
  read_back="$(redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$pass" GET "$KEY")"

  if [[ "$read_back" != "$value" ]]; then
    echo "[FAIL] tenant_$tenant round=$i write=$value read_back=${read_back:-<nil>}"
    exit 1
  fi

  echo "[OK] round=$i tenant=$tenant value=$value"

  if [[ "$SLEEP_SECONDS" != "0" ]]; then
    sleep "$SLEEP_SECONDS"
  fi
done

A_FINAL="$(redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" GET "$KEY")"
B_FINAL="$(redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_B_PASS" GET "$KEY")"

echo "tenant_a_final=${A_FINAL:-<nil>} expected=${LAST_A:-<nil>}"
echo "tenant_b_final=${B_FINAL:-<nil>} expected=${LAST_B:-<nil>}"

if [[ -n "$LAST_A" && "$A_FINAL" != "$LAST_A" ]]; then
  echo "[FAIL] Tenant A final value mismatch"
  exit 1
fi

if [[ -n "$LAST_B" && "$B_FINAL" != "$LAST_B" ]]; then
  echo "[FAIL] Tenant B final value mismatch"
  exit 1
fi

if [[ -n "$LAST_A" && -n "$LAST_B" && "$A_FINAL" == "$B_FINAL" ]]; then
  echo "[FAIL] Isolation check failed: tenant A and B share same value"
  exit 1
fi

echo "[OK] Round-robin 2-tenant test passed"
