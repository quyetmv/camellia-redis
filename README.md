# Camellia + Redis Multi-Tenant Lab (Docker)

Lab này bám mục tiêu PoC bạn đưa ra:
- 2 tenant
- 2 backend Redis (A/B), có thêm pool C để mô phỏng dedicated
- 1 lớp proxy (2 instance sau LB để mô phỏng HA data plane)
- test tách tenant
- test migrate tenant với endpoint client giữ nguyên

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
Prometheus (:9090) scrape /prometheus từ proxy
Grafana (:3000, admin/admin)
```

## 2) Vai trò thành phần (mapping A-E)

- A. `camellia-proxy-1`, `camellia-proxy-2`: data plane Redis protocol, auth, route theo tenant, metrics.
- B. `redis-pool-a`, `redis-pool-b`, `redis-pool-c`: backend tiers (`shared-small`, `shared-medium`, `dedicated`).
- C. `control-plane`: service quản trị tenant CRUD/migrate/tier + audit config change.
- D. Trong MVP lab này, dynamic config store dùng file `proxy/camellia-redis-proxy.properties` do control-plane quản lý; phù hợp mục tiêu validate kiến trúc và config-driven behavior.
- E. `prometheus`, `grafana`: connections, QPS, p95/p99, error, backend health, tenant-level command metrics.

## 3) Chạy lab

```bash
cd /mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis-lab
docker compose up -d --build
```

Kiểm tra nhanh:
```bash
./scripts/quick-check.sh
```

## 4) Test PoC

### 4.1 Test tách tenant
```bash
./scripts/test-separation.sh
```

### 4.2 Test migrate tenant A (endpoint không đổi)
```bash
./scripts/migrate-tenant-a.sh
```

Reset tenant A về pool A:
```bash
./scripts/reset-tenant-a.sh
```

## 5) Endpoint quan trọng

- Redis entrypoint (qua LB): `127.0.0.1:6379`
- Proxy console/metrics:
  - `http://127.0.0.1:16379/prometheus` (proxy-1)
  - `http://127.0.0.1:16380/prometheus` (proxy-2)
- Control plane: `http://127.0.0.1:18080`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (admin/admin)

Redis backend debug ports:
- Pool A: `127.0.0.1:63791`
- Pool B: `127.0.0.1:63792`
- Pool C: `127.0.0.1:63793`

## 6) Control plane API mẫu

Liệt kê tenant:
```bash
curl -s http://127.0.0.1:18080/tenants | jq
```

Tạo tenant mới:
```bash
curl -s -X POST http://127.0.0.1:18080/tenants \
  -H 'Content-Type: application/json' \
  -d '{
    "tenant_id":"tenant_c",
    "password":"tenantCpwd",
    "bid":3,
    "bgroup":"default",
    "tier":"dedicated"
  }' | jq
```

Migrate tenant sang backend khác:
```bash
curl -s -X POST http://127.0.0.1:18080/tenants/tenant_a/migrate \
  -H 'Content-Type: application/json' \
  -d '{"backend":"pool_b","tier":"shared-medium"}' | jq
```

Audit log:
```bash
curl -s 'http://127.0.0.1:18080/audit?limit=50' | jq
```

## 7) Metrics tối thiểu cho PoC

Các metric trọng tâm có sẵn từ Camellia:
- `redis_proxy_connect_count` (connections)
- `redis_proxy_total` / `redis_proxy_bid_bgroup` (qps/counter theo tenant)
- `redis_proxy_spend_stats{quantile="0.95|0.99"}` (p95/p99)
- `redis_proxy_fail` (error count)
- `redis_proxy_redis_connect_stats` (backend health)
- `redis_proxy_detail` (tenant-level command count)

## 8) Lưu ý

- Password tenant trong lab phải theo pattern `[A-Za-z0-9_]+` để match parser `multi_tenants_v1`.
- Lab này ưu tiên chứng minh `route abstraction`, `backend mobility`, `config-driven behavior`.
- Muốn dọn toàn bộ:
```bash
docker compose down -v
```
