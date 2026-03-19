#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
TENANT_A_PASS="${TENANT_A_PASS:-tenantApwd}"
TENANT_B_PASS="${TENANT_B_PASS:-tenantBpwd}"

REQUESTS="${REQUESTS:-100000}"
CLIENTS="${CLIENTS:-50}"
PIPELINE="${PIPELINE:-16}"
DATA_SIZE="${DATA_SIZE:-64}"
KEYSPACE="${KEYSPACE:-100000}"
PARALLEL="${PARALLEL:-1}"   # 1=run A/B together, 0=run sequential
CSV="${CSV:-0}"             # 1=redis-benchmark --csv
WORKLOAD_MODE="${WORKLOAD_MODE:-ratio}" # ratio|tests
SET_PERCENT="${SET_PERCENT:-30}"
GET_PERCENT="${GET_PERCENT:-70}"
TESTS="${TESTS:-set,get}"   # used when WORKLOAD_MODE=tests

OUT_BASE="${OUT_BASE:-./scripts/benchmark-results}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${OUT_BASE}/${RUN_ID}"

if ! command -v redis-benchmark >/dev/null 2>&1; then
  echo "[FAIL] redis-benchmark not found"
  exit 1
fi

mkdir -p "$OUT_DIR"

if [[ "$WORKLOAD_MODE" == "ratio" ]]; then
  if [[ "$SET_PERCENT" -lt 0 || "$GET_PERCENT" -lt 0 ]]; then
    echo "[FAIL] SET_PERCENT and GET_PERCENT must be >= 0"
    exit 1
  fi
  if [[ $((SET_PERCENT + GET_PERCENT)) -ne 100 ]]; then
    echo "[FAIL] SET_PERCENT + GET_PERCENT must equal 100"
    exit 1
  fi
fi

run_single() {
  local pass="$1"
  local test_name="$2"
  local requests="$3"
  local outfile="$4"

  if [[ "$requests" -le 0 ]]; then
    echo "[SKIP] test=$test_name requests=$requests" >>"$outfile"
    return
  fi

  local cmd=(
    redis-benchmark
    -h "$REDIS_HOST"
    -p "$REDIS_PORT"
    -a "$pass"
    -n "$requests"
    -c "$CLIENTS"
    -P "$PIPELINE"
    -d "$DATA_SIZE"
    -r "$KEYSPACE"
    -t "$test_name"
  )
  if [[ "$CSV" == "1" ]]; then
    cmd+=(--csv)
  fi

  "${cmd[@]}" >>"$outfile" 2>&1
}

run_benchmark() {
  local tenant="$1"
  local pass="$2"
  local outfile="$3"

  echo "[RUN] tenant=$tenant -> $outfile"
  {
    echo "[CONFIG] workload_mode=$WORKLOAD_MODE requests=$REQUESTS clients=$CLIENTS pipeline=$PIPELINE"
    if [[ "$WORKLOAD_MODE" == "ratio" ]]; then
      local set_requests get_requests
      set_requests=$((REQUESTS * SET_PERCENT / 100))
      get_requests=$((REQUESTS - set_requests))
      echo "[CONFIG] ratio=set:${SET_PERCENT}% get:${GET_PERCENT}% -> set_requests=$set_requests get_requests=$get_requests"
      run_single "$pass" "set" "$set_requests" "$outfile"
      run_single "$pass" "get" "$get_requests" "$outfile"
    else
      echo "[CONFIG] tests=$TESTS"
      run_single "$pass" "$TESTS" "$REQUESTS" "$outfile"
    fi
  } >"$outfile"
}

A_OUT="${OUT_DIR}/tenant-a.log"
B_OUT="${OUT_DIR}/tenant-b.log"

echo "[INFO] host=$REDIS_HOST port=$REDIS_PORT requests=$REQUESTS clients=$CLIENTS pipeline=$PIPELINE parallel=$PARALLEL workload_mode=$WORKLOAD_MODE"
if [[ "$WORKLOAD_MODE" == "ratio" ]]; then
  echo "[INFO] ratio=set:${SET_PERCENT}% get:${GET_PERCENT}%"
else
  echo "[INFO] tests=$TESTS"
fi

if [[ "$PARALLEL" == "1" ]]; then
  run_benchmark "A" "$TENANT_A_PASS" "$A_OUT" &
  pid_a=$!
  run_benchmark "B" "$TENANT_B_PASS" "$B_OUT" &
  pid_b=$!
  wait "$pid_a"
  wait "$pid_b"
else
  run_benchmark "A" "$TENANT_A_PASS" "$A_OUT"
  run_benchmark "B" "$TENANT_B_PASS" "$B_OUT"
fi

echo
echo "=== Summary ==="
for file in "$A_OUT" "$B_OUT"; do
  echo "--- $(basename "$file") ---"
  if rg -q "throughput summary:|^\"test\"" "$file"; then
    if [[ "$CSV" == "1" ]]; then
      rg -N '^"test"|^"set"|^"get"' "$file" || true
    elif [[ "$WORKLOAD_MODE" == "ratio" ]]; then
      mapfile -t throughput_lines < <(rg -N "throughput summary:" "$file" | sed 's/^[[:space:]]*//')
      if [[ "${#throughput_lines[@]}" -ge 1 ]]; then
        echo "SET -> ${throughput_lines[0]}"
      fi
      if [[ "${#throughput_lines[@]}" -ge 2 ]]; then
        echo "GET -> ${throughput_lines[1]}"
      fi
    else
      awk '
        {gsub(/\r/, "", $0)}
        $1=="======" {cmd=$2; next}
        /throughput summary:/ {
          line=$0
          sub(/^[[:space:]]+/, "", line)
          print cmd " -> " line
        }
      ' "$file" || true
    fi
  else
    tail -n 20 "$file"
  fi
done

echo
echo "[OK] Done. Raw logs at: $OUT_DIR"
