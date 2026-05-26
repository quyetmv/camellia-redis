#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
TENANT_A_PASS="${TENANT_A_PASS:-}"

REQUESTS="${REQUESTS:-100000}"
WARMUP_REQUESTS="${WARMUP_REQUESTS:-20000}"
WARMUP_PREFILL_REQUESTS="${WARMUP_PREFILL_REQUESTS:-100000}"

CLIENTS="${CLIENTS:-50}"
PIPELINE="${PIPELINE:-16}"
DATA_SIZE="${DATA_SIZE:-64}"
KEYSPACE="${KEYSPACE:-100000}"
CSV="${CSV:-0}"

SET_PERCENT=30
GET_PERCENT=70

OUT_BASE="${OUT_BASE:-./scripts/benchmark-results}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${OUT_BASE}/${RUN_ID}/tenant-a-warmup"
PREFILL_LOG="${OUT_DIR}/prefill.log"
WARMUP_LOG="${OUT_DIR}/warmup.log"
MAIN_LOG="${OUT_DIR}/main.log"

if ! command -v redis-benchmark >/dev/null 2>&1; then
  echo "[FAIL] redis-benchmark not found"
  exit 1
fi

mkdir -p "$OUT_DIR"

WARMUP_SET_REQUESTS=$((WARMUP_REQUESTS * SET_PERCENT / 100))
WARMUP_GET_REQUESTS=$((WARMUP_REQUESTS - WARMUP_SET_REQUESTS))
MAIN_SET_REQUESTS=$((REQUESTS * SET_PERCENT / 100))
MAIN_GET_REQUESTS=$((REQUESTS - MAIN_SET_REQUESTS))

run_benchmark() {
  local outfile="$1"
  local test_name="$2"
  local test_requests="$3"

  if [[ "$test_requests" -le 0 ]]; then
    echo "[SKIP] test=$test_name requests=$test_requests" >>"$outfile"
    return
  fi

  local cmd=(
    redis-benchmark
    -h "$REDIS_HOST"
    -p "$REDIS_PORT"
    -n "$test_requests"
    -c "$CLIENTS"
    -P "$PIPELINE"
    -d "$DATA_SIZE"
    -r "$KEYSPACE"
    -t "$test_name"
  )

  if [[ -n "$TENANT_A_PASS" ]]; then
    cmd+=(-a "$TENANT_A_PASS")
  fi

  if [[ "$CSV" == "1" ]]; then
    cmd+=(--csv)
  fi

  "${cmd[@]}" >>"$outfile" 2>&1
}

print_ratio() {
  echo "ratio=set:${SET_PERCENT}% get:${GET_PERCENT}%"
}

print_summary() {
  local title="$1"
  local logfile="$2"

  echo "=== ${title} ==="
  if [[ "$CSV" == "1" ]]; then
    rg -N '^"test"|^"set"|^"get"' "$logfile" || true
    return
  fi

  mapfile -t throughput_lines < <(rg -N "throughput summary:" "$logfile" | sed 's/^[[:space:]]*//')
  if [[ "${#throughput_lines[@]}" -ge 1 ]]; then
    echo "SET -> ${throughput_lines[0]}"
  fi
  if [[ "${#throughput_lines[@]}" -ge 2 ]]; then
    echo "GET -> ${throughput_lines[1]}"
  fi
}

AUTH_MODE="disabled"
if [[ -n "$TENANT_A_PASS" ]]; then
  AUTH_MODE="enabled"
fi

echo "[INFO] host=$REDIS_HOST port=$REDIS_PORT tenant=tenant_a auth=$AUTH_MODE" | tee "$PREFILL_LOG"
echo "[INFO] clients=$CLIENTS pipeline=$PIPELINE keyspace=$KEYSPACE data_size=$DATA_SIZE" | tee -a "$PREFILL_LOG"
echo "[INFO] prefill_requests=$WARMUP_PREFILL_REQUESTS warmup_requests=$WARMUP_REQUESTS main_requests=$REQUESTS" | tee -a "$PREFILL_LOG"
echo "[INFO] $(print_ratio)" | tee -a "$PREFILL_LOG"

echo "[RUN] Prefill keyspace"
run_benchmark "$PREFILL_LOG" "set" "$WARMUP_PREFILL_REQUESTS"

{
  echo "[INFO] warmup_requests=$WARMUP_REQUESTS"
  echo "[INFO] $(print_ratio)"
} >"$WARMUP_LOG"

echo "[RUN] Warmup"
run_benchmark "$WARMUP_LOG" "set" "$WARMUP_SET_REQUESTS"
run_benchmark "$WARMUP_LOG" "get" "$WARMUP_GET_REQUESTS"

{
  echo "[INFO] main_requests=$REQUESTS"
  echo "[INFO] $(print_ratio)"
} >"$MAIN_LOG"

echo "[RUN] Main benchmark"
run_benchmark "$MAIN_LOG" "set" "$MAIN_SET_REQUESTS"
run_benchmark "$MAIN_LOG" "get" "$MAIN_GET_REQUESTS"

echo
echo "=== Prefill ==="
if [[ "$CSV" == "1" ]]; then
  rg -N '^"test"|^"set"' "$PREFILL_LOG" || true
else
  prefill_line="$(rg -N "throughput summary:" "$PREFILL_LOG" | sed 's/^[[:space:]]*//' | tail -n 1)"
  if [[ -n "$prefill_line" ]]; then
    echo "SET -> $prefill_line"
  fi
fi

print_summary "Warmup" "$WARMUP_LOG"
print_summary "Main" "$MAIN_LOG"

echo
echo "[OK] Raw logs:"
echo "  $PREFILL_LOG"
echo "  $WARMUP_LOG"
echo "  $MAIN_LOG"
