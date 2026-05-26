#!/usr/bin/env bash
set -euo pipefail

DASHBOARD_URL="${DASHBOARD_URL:-http://127.0.0.1:18081}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[ERR] jq is required for this script"
  exit 1
fi

create_table() {
  local detail="$1"
  local info="$2"
  curl -fsS -X POST "$DASHBOARD_URL/camellia/admin/createResourceTable" \
    --data-urlencode "detail=$detail" \
    --data-urlencode "info=$info"
}

create_or_update_ref() {
  local bid="$1"
  local bgroup="$2"
  local tid="$3"
  local info="$4"
  curl -fsS -X POST "$DASHBOARD_URL/camellia/admin/createOrUpdateTableRef" \
    --data-urlencode "bid=$bid" \
    --data-urlencode "bgroup=$bgroup" \
    --data-urlencode "tid=$tid" \
    --data-urlencode "info=$info"
}

echo "[1/4] Create resource table for pool_a"
RESP_A="$(create_table "redis://@redis-pool-a:6379" "lab:pool_a:shared-small")"
TID_A="$(echo "$RESP_A" | jq -r '.data.tid')"
echo "[tid_a] $TID_A"

echo "[2/4] Create resource table for pool_b"
RESP_B="$(create_table "redis://@redis-pool-b:6379" "lab:pool_b:shared-medium")"
TID_B="$(echo "$RESP_B" | jq -r '.data.tid')"
echo "[tid_b] $TID_B"

echo "[3/4] Upsert bid=1,bgroup=default -> tid_a"
create_or_update_ref "1" "default" "$TID_A" "tenant_a route" | jq '.'

echo "[4/4] Upsert bid=2,bgroup=default -> tid_b"
create_or_update_ref "2" "default" "$TID_B" "tenant_b route" | jq '.'

echo "[OK] Dashboard bootstrap done"
echo "Try: curl -s \"$DASHBOARD_URL/camellia/api/resourceTable?bid=1&bgroup=default\" | jq"
