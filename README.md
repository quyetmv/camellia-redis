# Camellia + Redis Multi-Tenant Lab (Docker)

PoC mục tiêu:
- 2 tenant (`tenant_a`, `tenant_b`)
- 2 backend chính (pool A/B) + 1 pool C mô phỏng dedicated
- Proxy layer bằng Camellia Redis Proxy sau HAProxy
- Validate tách tenant, migrate tenant, config-driven routing
- Có metrics/log stack để quan sát tải

## 1) Topology

```text
Tenant clients (redis-cli/app/service)
        |
        v
  HAProxy (L4/TCP LB, :6379)
        |
  +-----+------------------+
  |                        |
Camellia Proxy #1      Camellia Proxy #2
(:6380, console :16379) (:6380, console :16379)
  |                        |
  +----- đọc cùng 1 dynamic config file ----+
        |
        +--> tenant A (password=tenantApwd) -> Redis Pool A
        +--> tenant B (password=tenantBpwd) -> Redis Pool B

Control Plane API (:18080) cập nhật route config + audit
Camellia Dashboard/Admin API (:18081) + MySQL/Redis metadata
Prometheus (:9090), Grafana (:3000)
```

Ngoài topology mặc định, lab có thêm cụm benchmark riêng tenant A:
- `camellia-proxy-tenant-a-1..6`
- `camellia-lb-tenant-a` expose `127.0.0.1:6381`

## 2) Mapping thành phần

- A. Data Plane: `camellia-proxy-*` nhận Redis protocol, auth, route tenant, expose metrics.
- B. Backend Pools: `redis-pool-a`, `redis-pool-b`, `redis-pool-c`.
- C. Control Plane: `control-plane` làm tenant CRUD/migrate/audit, không xử lý traffic Redis.
- D. Config/Admin: `camellia-dashboard` (build từ `../camellia-ref`), dùng như config center API.
- E. Observability: `prometheus` + `grafana`.

## 3) Run lab

```bash
cd /mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis
docker compose up -d --build
```

Quick check:
```bash
./scripts/quick-check.sh
```

Bootstrap config trên Camellia Dashboard (bid/bgroup 1,2):
```bash
bash ./scripts/dashboard-bootstrap.sh
```

## 4) Test PoC

Test tenant isolation:
```bash
./scripts/test-separation.sh
```

Test migrate tenant A (endpoint client giữ nguyên):
```bash
./scripts/migrate-tenant-a.sh
```

Reset tenant A về pool A:
```bash
./scripts/reset-tenant-a.sh
```

Round-robin ghi luân phiên 2 tenant:
```bash
bash ./scripts/round-robin-2-tenants.sh
```

## 5) Benchmark

Benchmark 2 tenant:
```bash
bash ./scripts/benchmark-2-tenants.sh
```

Ví dụ ratio 30% set / 70% get:
```bash
WORKLOAD_MODE=ratio SET_PERCENT=30 GET_PERCENT=70 REQUESTS=300000 CLIENTS=100 PIPELINE=32 PARALLEL=1 bash ./scripts/benchmark-2-tenants.sh
```

Benchmark riêng tenant A qua LB mặc định (`:6379`):
```bash
REDIS_PORT=6379 REQUESTS=300000 CLIENTS=100 PIPELINE=32 SET_PERCENT=30 GET_PERCENT=70 bash ./scripts/benchmark-tenant-a.sh
```

Chạy cụm 6 proxy riêng cho tenant A:
```bash
docker compose up -d \
  camellia-proxy-tenant-a-1 camellia-proxy-tenant-a-2 camellia-proxy-tenant-a-3 \
  camellia-proxy-tenant-a-4 camellia-proxy-tenant-a-5 camellia-proxy-tenant-a-6 \
  camellia-lb-tenant-a
```

Benchmark tenant A qua cụm 6 proxy (`:6381`):
```bash
REDIS_PORT=6381 REQUESTS=300000 CLIENTS=100 PIPELINE=32 SET_PERCENT=30 GET_PERCENT=70 bash ./scripts/benchmark-tenant-a.sh
```

Sweep tìm peak throughput trên cụm 6 proxy:
```bash
WORKERS=6 \
CLIENT_STEPS="120 240 480 720 960 1200" \
REQUESTS_PER_STEP=600000 \
PIPELINE=32 \
SET_PERCENT=30 GET_PERCENT=70 \
bash ./scripts/benchmark-tenant-a-6-proxy-max.sh
```

Output benchmark nằm trong:
```text
./scripts/benchmark-results/<timestamp>/
```

## 6) Endpoint

| Thành phần | Endpoint |
|---|---|
| Redis LB mặc định | `127.0.0.1:6379` |
| Redis LB cụm 6 proxy tenant A | `127.0.0.1:6381` |
| Proxy-1 metrics | `http://127.0.0.1:16379/prometheus` |
| Proxy-2 metrics | `http://127.0.0.1:16380/prometheus` |
| Control Plane | `http://127.0.0.1:18080` |
| Camellia Dashboard API | `http://127.0.0.1:18081` |
| Prometheus | `http://127.0.0.1:9090` |
| Grafana | `http://127.0.0.1:3000` (`admin/admin`) |
| Redis Pool A (debug) | `127.0.0.1:63791` |
| Redis Pool B (debug) | `127.0.0.1:63792` |
| Redis Pool C (debug) | `127.0.0.1:63793` |

## 7) API mẫu

List tenant:
```bash
curl -s http://127.0.0.1:18080/tenants | jq
```

Migrate tenant A sang pool B:
```bash
curl -s -X POST http://127.0.0.1:18080/tenants/tenant_a/migrate \
  -H 'Content-Type: application/json' \
  -d '{"backend":"pool_b","tier":"shared-medium"}' | jq
```

Audit log:
```bash
curl -s 'http://127.0.0.1:18080/audit?limit=50' | jq
```

Dashboard health:
```bash
curl -s http://127.0.0.1:18081/health/check | jq
```

Lấy route table theo bid/bgroup:
```bash
curl -s 'http://127.0.0.1:18081/camellia/api/resourceTable?bid=1&bgroup=default' | jq
```

## 8) Metrics cần theo dõi

- `redis_proxy_connect_count` (connections)
- `redis_proxy_total` / `redis_proxy_bid_bgroup` (QPS/counter theo tenant)
- `redis_proxy_spend_stats{quantile="0.95|0.99"}` (p95/p99)
- `redis_proxy_fail` (error count)
- `redis_proxy_redis_connect_stats` (backend health)
- `redis_proxy_detail` (tenant-level command stats)

## 9) Troubleshooting

`redis-cli` báo `Protocol error, got "H"`:
- Bạn đang kết nối nhầm vào HTTP port (ví dụ `16379`) thay vì Redis port (`6379` hoặc `6381`).

`ERR AUTH <password> called without any password configured`:
- Bạn đang bắn benchmark trực tiếp vào Redis backend (`63791/63792/63793`) thay vì proxy LB (`6379` hoặc `6381`).

Grafana không có data:
- Kiểm tra `http://127.0.0.1:9090/targets` phải thấy targets `UP`.
- Chạy traffic test trước (`test-separation.sh` hoặc benchmark scripts) để có metrics.

## 10) Cleanup

```bash
docker compose down -v
```
