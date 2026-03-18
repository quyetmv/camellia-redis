#!/usr/bin/env bash
set -euo pipefail

echo "== Health =="
curl -fsS http://127.0.0.1:18080/healthz | sed 's/^/[control-plane] /'

echo "== Dashboard health (optional in lab) =="
if curl -fsS http://127.0.0.1:18081/health/check >/dev/null 2>&1; then
  curl -fsS http://127.0.0.1:18081/health/check | sed 's/^/[dashboard] /'
else
  echo "[dashboard] unavailable (skip)"
fi

echo "== Proxy metrics endpoint =="
curl -fsS http://127.0.0.1:16379/prometheus | head -n 20

echo "== Current tenants =="
curl -fsS http://127.0.0.1:18080/tenants | sed 's/^/[tenants] /'
