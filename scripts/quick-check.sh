#!/usr/bin/env bash
set -euo pipefail

echo "== Health =="
curl -fsS http://127.0.0.1:18080/healthz | sed 's/^/[control-plane] /'

echo "== Proxy metrics endpoint =="
curl -fsS http://127.0.0.1:16379/prometheus | head -n 20

echo "== Current tenants =="
curl -fsS http://127.0.0.1:18080/tenants | sed 's/^/[tenants] /'
