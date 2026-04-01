# Camellia Test Runner Troubleshooting

## 1) Không thấy log test (chỉ thấy waiting)

### Triệu chứng
- `kubectl logs -f` chỉ hiện `Waiting for logs...`

### Nguyên nhân
- Container command đang là `sleep ...`, không chạy script test.

### Cách xử lý
- Dùng command chạy test:
  - `python -u /app/run-tests.py`
- File tham chiếu:
  - `k8s/test-runner/camellia-test-runner-deployment.yaml`


## 2) Lỗi `Redis Cluster cannot be connected... Cluster mode is not enabled on this node`

### Triệu chứng
- Test scenario `cluster` fail ngay khi khởi tạo `RedisCluster`.

### Nguyên nhân
- `RedisCluster` bootstrap qua service proxy có thể không ổn định theo endpoint/slot-map tại thời điểm connect.
- Có trường hợp proxy trả lời chưa phù hợp với kỳ vọng bootstrap của redis-py cluster client.

### Cách xử lý
- Trong test-runner, dùng `redis.Redis` + tự xử lý `MOVED` redirect (retry theo host/port trả về).
- Tách logic test khỏi phụ thuộc bootstrap cluster client.


## 3) Lỗi `MOVED <slot> <host>:6380`

### Triệu chứng
- P1/P2/P3 pass/fail ngẫu nhiên theo lần chạy.

### Nguyên nhân
- Client không follow redirect hoặc slot-map cluster đang rebalance/đổi leader.

### Cách xử lý
- Bắt `ResponseError` chứa `MOVED`, parse host/port, tạo lại connection và retry lệnh.
- Giữ interval test đủ lớn để giảm nhiễu khi cluster đang converge.


## 4) Shared-auth fail khi test bằng mode cluster client

### Triệu chứng
- Tenant auth fail hoặc kết quả đọc key không đúng kỳ vọng.

### Nguyên nhân
- Shared-auth phụ thuộc password tenant; dùng cluster bootstrap client dễ gây hành vi không mong muốn trong test flow.

### Cách xử lý
- Dùng Redis client thường cho shared-auth test.
- Kiểm tra password tenant đúng cấu hình (`svcOrderPwd`, `svcPaymentPwd`, ...).


## 5) Multi-key fail trong cluster (`MGET`/pipeline)

### Triệu chứng
- P3 fail do key nằm khác slot.

### Nguyên nhân
- Cluster yêu cầu multi-key cùng slot.

### Cách xử lý
- Dùng hash-tag trong key, ví dụ:
  - `k8s:runner:cluster:{tenant}:1`
  - `k8s:runner:cluster:{tenant}:2`


## 6) Log lỗi `client command syntax error, arg = SETINFO`

### Triệu chứng
- Camellia log error định kỳ từ `CLIENT SETINFO`.

### Nguyên nhân
- redis-py gửi metadata command mà proxy/backend không hỗ trợ đầy đủ.

### Cách xử lý
- Trên Redis client kwargs:
  - `lib_name=None`
  - `lib_version=None`


## 7) Lỗi route config reload liên tục

### Triệu chứng
- `missing 'route.conf' and 'route.conf.file'` lặp lại.

### Nguyên nhân
- Thiếu cấu hình route trong profile properties đang mount vào proxy.

### Cách xử lý
- Đảm bảo có `route.conf` hoặc `route.conf.file` trong file properties tương ứng deployment.
- Kiểm tra ConfigMap mount path và tên file properties đang dùng.


## 8) Command kiểm tra nhanh

```bash
# rollout test-runner
kubectl -n testing rollout restart deploy/camellia-test-runner
kubectl -n testing rollout status deploy/camellia-test-runner

# xem log test-runner
kubectl -n testing logs -f deploy/camellia-test-runner

# kiểm tra cluster proxy có bật cluster mode không
redis-cli -h svc-camellia-proxy-cluster-key-routing -p 6380 -a camellia_admin_pass cluster info

# kiểm tra env trong pod test-runner
kubectl -n testing exec -it deploy/camellia-test-runner -- env | grep -E 'TEST_SCENARIO|KEY_ROUTING|SHARED_AUTH|RUN_'
```


## 9) Test-runner hiện kiểm gì

- Preflight:
  - key-routing cơ bản qua admin endpoint
  - shared-auth route cho `order/payment/search`
  - multi-key cùng slot
- Stress workload:
  - nhiều client đồng thời
  - ratio `SET/GET`
  - prefix riêng theo service
  - phân phối `hot key` có chủ đích
  - summary `throughput`, `latency avg/p95/p99`, `bytes`, `failures`

Biến môi trường mới:

- `ORDER_PASSWORD`, `PAYMENT_PASSWORD`, `SEARCH_PASSWORD`
- `ORDER_SERVICE_PREFIX`, `PAYMENT_SERVICE_PREFIX`, `SEARCH_SERVICE_PREFIX`
- `HOT_KEY_NAME`
- `STRESS_CLIENTS`
- `STRESS_REQUESTS_PER_CLIENT`
- `SET_PERCENT`, `GET_PERCENT`
- `HOT_KEY_PERCENT`, `HOT_KEY_COUNT`
- `KEYSPACE`
- `VALUE_SIZE`
- `REPORT_EVERY`
- `SCENARIO_DELAY_SECONDS`


## 10) Gợi ý cấu hình ổn định

- `TEST_SCENARIO=both` để chạy tuần tự cả `cluster` và `standalone`.
- `RUN_INTERVAL_SECONDS=60` (hoặc cao hơn khi cluster đang scale/rebalance).
- Giữ một deployment test-runner, chỉ đổi scenario bằng env.


## 11) Note migration: từ Redis Sentinel/Cluster sang Camellia

### 11.1 Về topology và semantics
- Camellia `sharding` trên nhiều Redis standalone **không phải** Redis Cluster native.
- Nếu app đang dùng Redis Cluster client, cần chuẩn hóa lại hành vi:
  - nên đi qua endpoint Camellia bằng Redis client thường (hoặc kiểm thử kỹ logic redirect).
- Xác nhận lại semantics multi-key:
  - với mode cluster, các lệnh multi-key vẫn chịu ràng buộc slot; dùng hash-tag khi cần cùng slot.

### 11.2 Về auth và tenant routing
- Camellia có thể route theo password tenant (`shared-auth`), khác mô hình auth của Redis/Sentinel cũ.
- Checklist:
  - map rõ `tenant -> password -> bid/bgroup/route`.
  - tách `admin password` và `tenant password`, không dùng lẫn.

### 11.3 Về failover và endpoint
- Sentinel failover cũ là ở tầng Redis master/replica.
- Với Camellia, failover có thêm tầng proxy + (nếu bật) consensus/leader.
- Cần test đủ các tình huống:
  - mất 1 proxy node,
  - đổi leader consensus,
  - mất 1 backend shard,
  - rolling restart.

### 11.4 Về dữ liệu và phân phối key
- Trước cutover, thống kê keyspace để tránh lệch tải shard sau khi đổi route.
- Nếu đổi chiến lược route (theo key/prefix/tenant), cần đánh giá:
  - tỷ lệ hot key,
  - phân bố QPS theo shard,
  - kích thước key/value theo shard.

### 11.5 Về tương thích lệnh
- Kiểm tra các lệnh app đang dùng có tương thích qua proxy (đặc biệt Lua/script, transaction, pub/sub, scan pattern lớn).
- Kiểm tra command do client tự gửi (ví dụ `CLIENT SETINFO`) để tránh log nhiễu/error giả.

### 11.6 Về timeout/pool/retry
- Khi thêm tầng proxy, cần tuning lại:
  - connect timeout,
  - socket timeout,
  - retry/backoff,
  - pool size mỗi app instance.
- Tránh retry quá aggressive gây bão lệnh khi backend chập chờn.

### 11.7 Về quan sát và cảnh báo
- Bật metric và dashboard cho cả 2 tầng: Camellia + Redis backend.
- Tối thiểu cần alert:
  - lỗi auth theo tenant,
  - tỉ lệ MOVED/NOT_AVAILABLE tăng,
  - latency p95/p99 tăng,
  - fail connect backend,
  - hot key/big key.

### 11.8 Về rollout an toàn
- Khuyến nghị rollout theo pha:
  1. Shadow read / canary 1 phần traffic.
  2. So sánh latency + error rate với hệ cũ.
  3. Cutover tăng dần.
  4. Giữ rollback plan rõ ràng (DNS/service switch, config version pin).


## 12) Sentinel, sharding và test-runner

- Nếu backend là nhiều cụm Redis Sentinel, mỗi cụm Sentinel nên được biểu diễn thành một resource `redis-sentinel://.../master-name?...`.
- Khi ghép nhiều cụm thành sharding, Camellia route theo bucket/key; Sentinel chỉ lo failover trong từng shard.
- Test-runner hiện không bootstrap Sentinel trực tiếp. Nó kiểm từ góc nhìn ứng dụng sau cutover, tức là app chỉ nói chuyện với Camellia endpoint.
- Muốn kiểm migration từ app `redis-sentinel` cũ:
  - giữ nguyên tập lệnh app-level `SET/GET/MGET`,
  - đổi connection sang Camellia,
  - chạy `P2/P4/P5` để xác thực isolation, prefix namespace và hot-key path.
