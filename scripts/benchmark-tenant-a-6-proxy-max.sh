#!/usr/bin/env bash
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6381}"
TENANT_A_PASS="${TENANT_A_PASS:-tenantApwd}"

WORKERS="${WORKERS:-6}"
CLIENT_STEPS="${CLIENT_STEPS:-120 240 480 720 960 1200}"
REQUESTS_PER_STEP="${REQUESTS_PER_STEP:-600000}"
PIPELINE="${PIPELINE:-32}"
DATA_SIZE="${DATA_SIZE:-64}"
KEYSPACE="${KEYSPACE:-1000000}"

SET_PERCENT="${SET_PERCENT:-30}"
GET_PERCENT="${GET_PERCENT:-70}"

OUT_BASE="${OUT_BASE:-./scripts/benchmark-results}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${OUT_BASE}/${RUN_ID}/tenant-a-6-proxy-max"
RESULT_FILE="${OUT_DIR}/summary.tsv"

if ! command -v redis-benchmark >/dev/null 2>&1; then
  echo "[FAIL] redis-benchmark not found"
  exit 1
fi

if ! command -v redis-cli >/dev/null 2>&1; then
  echo "[FAIL] redis-cli not found"
  exit 1
fi

if [[ "$WORKERS" -le 0 ]]; then
  echo "[FAIL] WORKERS must be > 0"
  exit 1
fi

if [[ "$REQUESTS_PER_STEP" -le 0 ]]; then
  echo "[FAIL] REQUESTS_PER_STEP must be > 0"
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

mkdir -p "$OUT_DIR"

if ! redis-cli --raw -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$TENANT_A_PASS" PING >/dev/null 2>&1; then
  echo "[FAIL] Cannot PING proxy endpoint ${REDIS_HOST}:${REDIS_PORT} with tenant A credentials"
  exit 1
fi

extract_rps() {
  local file="$1"
  sed -n 's/.*throughput summary: \([0-9.]\+\) requests per second.*/\1/p' "$file" | tail -n 1
}

sum_rps() {
  awk '{s+=$1} END{printf "%.2f", s+0}'
}

echo -e "clients_total\tset_rps\tget_rps\ttotal_rps" >"$RESULT_FILE"

echo "[INFO] host=$REDIS_HOST port=$REDIS_PORT workers=$WORKERS"
echo "[INFO] ratio=set:${SET_PERCENT}% get:${GET_PERCENT}% requests_per_step=$REQUESTS_PER_STEP pipeline=$PIPELINE"
echo
printf "%-14s %-14s %-14s %-14s\n" "clients_total" "set_rps" "get_rps" "total_rps"
printf "%-14s %-14s %-14s %-14s\n" "------------" "-------" "-------" "---------"

best_clients=""
best_total="0"

for clients_total in $CLIENT_STEPS; do
  if [[ "$clients_total" -le 0 ]]; then
    echo "[SKIP] clients_total=$clients_total"
    continue
  fi

  step_dir="${OUT_DIR}/clients-${clients_total}"
  mkdir -p "$step_dir"

  clients_base=$((clients_total / WORKERS))
  clients_extra=$((clients_total % WORKERS))

  requests_base=$((REQUESTS_PER_STEP / WORKERS))
  requests_extra=$((REQUESTS_PER_STEP % WORKERS))

  pids=()
  set_logs=()
  get_logs=()

  for ((i = 1; i <= WORKERS; i++)); do
    worker_clients="$clients_base"
    if [[ "$i" -le "$clients_extra" ]]; then
      worker_clients=$((worker_clients + 1))
    fi
    if [[ "$worker_clients" -le 0 ]]; then
      worker_clients=1
    fi

    worker_requests="$requests_base"
    if [[ "$i" -le "$requests_extra" ]]; then
      worker_requests=$((worker_requests + 1))
    fi

    set_requests=$((worker_requests * SET_PERCENT / 100))
    get_requests=$((worker_requests - set_requests))

    set_clients=$((worker_clients * SET_PERCENT / 100))
    get_clients=$((worker_clients - set_clients))
    if [[ "$set_requests" -gt 0 && "$set_clients" -le 0 ]]; then
      set_clients=1
      get_clients=$((worker_clients - set_clients))
    fi
    if [[ "$get_requests" -gt 0 && "$get_clients" -le 0 ]]; then
      get_clients=1
      set_clients=$((worker_clients - get_clients))
    fi
    if [[ "$set_clients" -le 0 ]]; then
      set_clients=1
    fi
    if [[ "$get_clients" -le 0 ]]; then
      get_clients=1
    fi

    set_log="${step_dir}/worker-${i}-set.log"
    get_log="${step_dir}/worker-${i}-get.log"
    set_logs+=("$set_log")
    get_logs+=("$get_log")

    if [[ "$set_requests" -gt 0 ]]; then
      redis-benchmark \
        -h "$REDIS_HOST" \
        -p "$REDIS_PORT" \
        -a "$TENANT_A_PASS" \
        -n "$set_requests" \
        -c "$set_clients" \
        -P "$PIPELINE" \
        -d "$DATA_SIZE" \
        -r "$KEYSPACE" \
        -t set >"$set_log" 2>&1 &
      pids+=("$!")
    else
      echo "[SKIP] set_requests=0" >"$set_log"
    fi

    if [[ "$get_requests" -gt 0 ]]; then
      redis-benchmark \
        -h "$REDIS_HOST" \
        -p "$REDIS_PORT" \
        -a "$TENANT_A_PASS" \
        -n "$get_requests" \
        -c "$get_clients" \
        -P "$PIPELINE" \
        -d "$DATA_SIZE" \
        -r "$KEYSPACE" \
        -t get >"$get_log" 2>&1 &
      pids+=("$!")
    else
      echo "[SKIP] get_requests=0" >"$get_log"
    fi
  done

  failed=0
  for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
      failed=1
    fi
  done
  if [[ "$failed" -ne 0 ]]; then
    echo "[FAIL] benchmark process failed for clients_total=$clients_total (check $step_dir)"
    exit 1
  fi

  set_rps_total="$(for log in "${set_logs[@]}"; do extract_rps "$log"; done | awk 'NF>0' | sum_rps)"
  get_rps_total="$(for log in "${get_logs[@]}"; do extract_rps "$log"; done | awk 'NF>0' | sum_rps)"
  total_rps="$(awk -v a="$set_rps_total" -v b="$get_rps_total" 'BEGIN{printf "%.2f", a+b}')"

  printf "%-14s %-14s %-14s %-14s\n" "$clients_total" "$set_rps_total" "$get_rps_total" "$total_rps"
  echo -e "${clients_total}\t${set_rps_total}\t${get_rps_total}\t${total_rps}" >>"$RESULT_FILE"

  is_better="$(awk -v cur="$total_rps" -v best="$best_total" 'BEGIN{print (cur>best)?1:0}')"
  if [[ "$is_better" == "1" ]]; then
    best_total="$total_rps"
    best_clients="$clients_total"
  fi
done

echo
echo "=== Best observed throughput ==="
echo "clients_total=$best_clients total_rps=$best_total"
echo "[OK] Full logs: $OUT_DIR"
