#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
TENANT_A_PASS="${TENANT_A_PASS:-tenantApwd}"

REQUESTS="${REQUESTS:-100000}"
CLIENTS="${CLIENTS:-50}"
PIPELINE="${PIPELINE:-16}"
DATA_SIZE="${DATA_SIZE:-64}"
KEYSPACE="${KEYSPACE:-100000}"

SET_PERCENT="${SET_PERCENT:-30}"
GET_PERCENT="${GET_PERCENT:-70}"
CSV="${CSV:-0}"

OUT_BASE="${OUT_BASE:-./scripts/benchmark-results}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="${OUT_BASE}/${RUN_ID}/tenant-a.log"

if ! command -v redis-benchmark >/dev/null 2>&1; then
  echo "[FAIL] redis-benchmark not found"
  exit 1
fi

if [[ "$SET_PERCENT" -lt 0 || "$GET_PERCENT" -lt 0 ]]; then
  echo "[FAIL] SET_PERCENT and GET_PERCENT must be >= 0"
  exit 1
fi
if [[ $((SET_PERCENT + GET_PERCENT)) -ne 100 ]]; then
  echo "[FAIL] SET_PERCENT + GET_PERCENT must equal 100"
  exit 1
fi

mkdir -p "$(dirname "$OUT_FILE")"

SET_REQUESTS=$((REQUESTS * SET_PERCENT / 100))
GET_REQUESTS=$((REQUESTS - SET_REQUESTS))

run_one() {
  local test_name="$1"
  local test_requests="$2"
  if [[ "$test_requests" -le 0 ]]; then
    return
  fi

  local cmd=(
    redis-benchmark
    -h "$REDIS_HOST"
    -p "$REDIS_PORT"
    -a "$TENANT_A_PASS"
    -n "$test_requests"
    -c "$CLIENTS"
    -P "$PIPELINE"
    -d "$DATA_SIZE"
    -r "$KEYSPACE"
    -t "$test_name"
  )

  if [[ "$CSV" == "1" ]]; then
    cmd+=(--csv)
  fi

  "${cmd[@]}" >>"$OUT_FILE" 2>&1
}

echo "[INFO] host=$REDIS_HOST port=$REDIS_PORT tenant=tenant_a requests=$REQUESTS clients=$CLIENTS pipeline=$PIPELINE" | tee "$OUT_FILE"
echo "[INFO] ratio=set:${SET_PERCENT}% get:${GET_PERCENT}% -> set_requests=$SET_REQUESTS get_requests=$GET_REQUESTS" | tee -a "$OUT_FILE"

run_one set "$SET_REQUESTS"
run_one get "$GET_REQUESTS"

echo
echo "=== Summary (tenant-a) ==="
if [[ "$CSV" == "1" ]]; then
  rg -N '^"test"|^"set"|^"get"' "$OUT_FILE" || true
else
  mapfile -t throughput_lines < <(rg -N "throughput summary:" "$OUT_FILE" | sed 's/^[[:space:]]*//')
  if [[ "${#throughput_lines[@]}" -ge 1 ]]; then
    echo "SET -> ${throughput_lines[0]}"
  fi
  if [[ "${#throughput_lines[@]}" -ge 2 ]]; then
    echo "GET -> ${throughput_lines[1]}"
  fi
fi

echo "[OK] Raw log: $OUT_FILE"
