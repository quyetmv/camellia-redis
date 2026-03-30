# Camellia Redis Proxy on Kubernetes

README này mô tả cách deploy bộ manifest trong thư mục `k8s/` theo hướng tham chiếu tài liệu Camellia Redis Proxy `1.3.7`.

Layout đã được quy hoạch lại để dễ đọc hơn:

- Proxy chạy trên Kubernetes
- Redis backend cũng chạy trên Kubernetes
- Route config dùng `local + resource-sharding-singlewrite-multiread.json`
- Monitoring expose qua console HTTP `/prometheus`

Topology mặc định khuyến nghị:

- `Deployment + NodePort Service`
- Scale ngang nhiều pod Camellia proxy để Service phân phối connection vào các pod
- Phù hợp hơn `StatefulSet` cho lab này vì proxy đang stateless theo `ConfigMap`

Lưu ý quan trọng:

- Bộ manifest này đang theo mô hình `sharding local transpond`, không phải mô hình `multi_tenants_v1` trong lab Docker Compose.
- Nghĩa là proxy route theo `resource-sharding-singlewrite-multiread.json`, không route theo password tenant.
- Nếu muốn multi-tenant giống Docker lab, cần đổi lại config proxy sang mode `route.conf.provider=multi_tenants_v1`.

## 1. Cấu trúc thư mục

```text
k8s/
├── README.md
├── base/
│   ├── camellia-proxy-configmap.yaml
│   ├── redis-backends.yaml
│   └── kustomization.yaml
├── monitoring/
│   ├── camellia-proxy-servicemonitor.yaml
│   ├── redis-backend-servicemonitor.yaml
│   └── kustomization.yaml
├── grafana/
│   ├── redis-backend-dashboard.json
│   ├── redis-backend-dashboard-configmap.yaml
│   └── kustomization.yaml
├── benchmark/
│   ├── redis-benchmark-client-deployment.yaml
│   └── kustomization.yaml
├── statefulset/
│   ├── camellia-proxy-statefulset.yaml
│   ├── camellia-proxy-service.yaml
│   └── kustomization.yaml
└── deployment/
    ├── cluster/
    │   ├── camellia-proxy-cluster-deployment.yaml
    │   ├── camellia-proxy-cluster-service.yaml
    │   └── kustomization.yaml
    └── standalone/
        ├── camellia-proxy-standalone-deployment.yaml
        ├── camellia-proxy-standalone-service.yaml
        └── kustomization.yaml
```

Ý nghĩa:

- `base/`: tài nguyên dùng chung, gồm `ConfigMap` và 9 Redis backend
- `monitoring/`: `ServiceMonitor` để Prometheus Operator scrape metrics từ Camellia proxy và Redis backend
- `grafana/`: dashboard JSON và `ConfigMap` import dashboard Redis backend vào Grafana nếu cluster có sidecar đọc label `grafana_dashboard=1`
- `benchmark/`: benchmark client pod để chạy `redis-benchmark` trong cluster
- `statefulset/`: topology proxy kiểu `StatefulSet`
- `deployment/cluster/`: overlay `cluster`, mount `application-cluster.yml`
- `deployment/standalone/`: overlay `standalone`, mount `application-standalone.yml`

Tên file đã được đổi theo vai trò để nhìn vào là biết dùng để làm gì.

## 1.1 Kustomization

Mỗi thư mục `base/`, `monitoring/`, `grafana/`, `statefulset/`, `deployment/cluster/`, `deployment/standalone/`, `benchmark/` đều có file `kustomization.yaml`.

Vai trò:

- `base/kustomization.yaml`: gom `camellia-proxy-configmap.yaml` và `redis-backends.yaml`
- `monitoring/kustomization.yaml`: gom `camellia-proxy-servicemonitor.yaml` và `redis-backend-servicemonitor.yaml`
- `grafana/kustomization.yaml`: gom `redis-backend-dashboard-configmap.yaml`
- `statefulset/kustomization.yaml`: include `../base` + proxy `StatefulSet` + service của `StatefulSet`
- `deployment/cluster/kustomization.yaml`: include `../../base` + proxy `Deployment` `cluster`
- `deployment/standalone/kustomization.yaml`: include `../../base` + proxy `Deployment` `standalone`
- `benchmark/kustomization.yaml`: tạo một pod client để chạy `redis-benchmark`

Lệnh chạy chính:

```bash
cd /mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis/k8s
kubectl apply -n testing -k ./base
kubectl apply -n testing -k ./monitoring
kubectl apply -n monitoring -k ./grafana
kubectl apply -n testing -k ./statefulset
kubectl apply -n testing -k ./deployment/standalone
kubectl apply -n testing -k ./deployment/cluster
kubectl apply -n testing -k ./benchmark
```

Nếu chỉ muốn xem YAML sau khi render bởi Kustomize:

```bash
kubectl kustomize ./base
kubectl kustomize ./monitoring
kubectl kustomize ./grafana
kubectl kustomize ./statefulset
kubectl kustomize ./deployment/standalone
kubectl kustomize ./deployment/cluster
kubectl kustomize ./benchmark
```

Nếu máy đã cài binary `kustomize` riêng:

```bash
kustomize build ./base
kustomize build ./monitoring
kustomize build ./grafana
kustomize build ./statefulset
kustomize build ./deployment/standalone
kustomize build ./deployment/cluster
kustomize build ./benchmark
```

Bạn chỉ nên chọn 1 trong 2 cách chạy proxy:

1. `Deployment`: topology mặc định, dùng profile `cluster`
2. `StatefulSet`: topology tuỳ chọn, chỉ dùng khi cần test semantic của `StatefulSet`

## 2. Topology

```text
                          +----------------------+
                          |      client app      |
                          | redis-cli / service  |
                          +----------+-----------+
                                     |
                                     v
                    +----------------------------------+
                    | svc-camellia-proxy-cluster      |
                    | NodePort 30480                  |
                    | console 30479                   |
                    +----------------+-----------------+
                                     |
                                     v
                    +----------------------------------+
                    | Deployment proxy                 |
                    | deploy-camellia-proxy-cluster   |
                    | replicas = 3                    |
                    | pod labels:                     |
                    |   app=camellia-proxy-cluster    |
                    +----------------+-----------------+
                                     |
                                     v
                    +--------------------------------------+
                    | ConfigMap cm-db-camellia             |
                    | - application.yml                    |
                    | - resource-sharding-singlewrite-     |
                    |   multiread.json                     |
                    | - logback.xml                        |
                    +----------------+---------------------+
                                     |
                                     v
                    +--------------------------------------+
                    | Camellia local transpond             |
                    | type=complex, json-file=resource-    |
                    | table.json, bucketSize=3             |
                    +----------------+---------------------+
                                     |
                                     v
      +-----------+-----------+-----------+-----------+-----------+-----------+-----------+-----------+-----------+
      |           |           |           |           |           |           |           |           |           |
      v           v           v           v           v           v           v           v           v
 +----------+ +----------+ +----------+ +----------+ +----------+ +----------+ +----------+ +----------+ +----------+
 | pool-1   | | pool-2   | | pool-3   | | pool-4   | | pool-5   | | pool-6   | | pool-7   | | pool-8   | | pool-9   |
 | :6379    | | :6379    | | :6379    | | :6379    | | :6379    | | :6379    | | :6379    | | :6379    | | :6379    |
 +----------+ +----------+ +----------+ +----------+ +----------+ +----------+ +----------+ +----------+ +----------+

Metrics endpoint:
  http://<proxy-host>:16379/prometheus
```

Nếu cluster dùng Prometheus Operator hoặc `kube-prometheus-stack`, có thể thêm `ServiceMonitor` để scrape metrics qua service port `console`.

Topology tuỳ chọn `StatefulSet`:

```text
client
  |
  v
svc-db-camellia (NodePort 30380)
  |
  v
sts-db-camellia
  |
  v
same ConfigMap + same Redis backends
```

Trong `resource-sharding-singlewrite-multiread.json`, proxy đang dùng sharding `bucketSize=3` với `single write / multiple read`:

- bucket `0`: write `redis-pool-1`, read random từ `redis-pool-2`, `redis-pool-3`
- bucket `1`: write `redis-pool-4`, read random từ `redis-pool-5`, `redis-pool-6`
- bucket `2`: write `redis-pool-7`, read random từ `redis-pool-8`, `redis-pool-9`

## 3. Preconditions

Cần có:

- `kubectl`
- một cluster Kubernetes đang truy cập được
- namespace deploy, ví dụ `testing`

Kiểm tra context hiện tại:

```bash
cd /mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis/k8s
kubectl config current-context
kubectl get ns
```

Tạo namespace nếu chưa có:

```bash
kubectl create namespace testing
```

## 4. Deploy base resources

`base/` gồm:

- `cm-db-camellia`
- `redis-pool-1`
- `redis-pool-2`
- `redis-pool-3`
- `redis-pool-4`
- `redis-pool-5`
- `redis-pool-6`
- `redis-pool-7`
- `redis-pool-8`
- `redis-pool-9`

Apply:

```bash
kubectl apply -n testing -k ./base
```

Kiểm tra:

```bash
kubectl get configmap -n testing cm-db-camellia
kubectl get pods -n testing -l app=redis-pool-1
kubectl get pods -n testing -l app=redis-pool-2
kubectl get pods -n testing -l app=redis-pool-3
kubectl get pods -n testing -l app=redis-pool-4
kubectl get pods -n testing -l app=redis-pool-5
kubectl get pods -n testing -l app=redis-pool-6
kubectl get pods -n testing -l app=redis-pool-7
kubectl get pods -n testing -l app=redis-pool-8
kubectl get pods -n testing -l app=redis-pool-9
kubectl get svc -n testing | grep redis-pool
```

Rollout status:

```bash
kubectl rollout status deployment/redis-pool-1 -n testing
kubectl rollout status deployment/redis-pool-2 -n testing
kubectl rollout status deployment/redis-pool-3 -n testing
kubectl rollout status deployment/redis-pool-4 -n testing
kubectl rollout status deployment/redis-pool-5 -n testing
kubectl rollout status deployment/redis-pool-6 -n testing
kubectl rollout status deployment/redis-pool-7 -n testing
kubectl rollout status deployment/redis-pool-8 -n testing
kubectl rollout status deployment/redis-pool-9 -n testing
```

## 4.1 Deploy ServiceMonitor

Phần này chỉ cần khi cluster đã có CRD `ServiceMonitor` và có Prometheus Operator đang watch namespace `testing`.

Kiểm tra CRD:

```bash
kubectl get crd servicemonitors.monitoring.coreos.com
```

Apply:

```bash
kubectl apply -n testing -k ./monitoring
```

Kiểm tra:

```bash
kubectl get servicemonitor -n testing
kubectl describe servicemonitor camellia-proxy -n testing
kubectl describe servicemonitor redis-backend -n testing
```

ServiceMonitor này sẽ scrape mọi service Camellia proxy có label:

- `monitoring.camellia.io/enabled=true`

ServiceMonitor Redis backend sẽ scrape mọi service có label:

- `monitoring.redis.io/enabled=true`

Endpoint scrape:

- Camellia proxy: `port=console`, `path=/prometheus`
- Redis backend exporter: `port=metrics`, `path=/metrics`

Lưu ý:

- Nếu dùng `kube-prometheus-stack`, Prometheus instance của bạn có thể chỉ select `ServiceMonitor` có thêm label như `release: kube-prometheus-stack`.
- Nếu gặp trường hợp đó, patch thêm label vào cả `monitoring/camellia-proxy-servicemonitor.yaml` và `monitoring/redis-backend-servicemonitor.yaml`.

## 5. Chạy proxy bằng Deployment

Đây là topology mặc định nên dùng cho lab này.

Lý do:

- Camellia proxy trong lab đang stateless theo `ConfigMap`
- Cần scale ngang nhiều pod để `Service` phân phối connection
- Không cần stable identity của `StatefulSet`

Apply:

```bash
kubectl apply -n testing -k ./deployment/cluster
```

Kiểm tra:

```bash
kubectl get deploy,pods,svc -n testing | grep camellia
kubectl rollout status deployment/deploy-camellia-proxy-cluster -n testing
```

Scale thêm nếu cần:

```bash
kubectl scale deployment deploy-camellia-proxy-cluster -n testing --replicas=6
```

NodePort của `Deployment` service:

- Redis proxy: `30480`
- Console/metrics: `30479`

Port-forward:

```bash
kubectl port-forward -n testing svc/svc-camellia-proxy-cluster 6380:6380 16379:16379
```

## 6. Chạy proxy bằng StatefulSet

Đây là topology tuỳ chọn. Chỉ dùng khi muốn test behavior của `StatefulSet`.

Apply:

```bash
kubectl apply -n testing -k ./statefulset
```

Kiểm tra:

```bash
kubectl get sts,pods,svc -n testing | grep camellia
kubectl rollout status statefulset/sts-db-camellia -n testing
```

Logs:

```bash
kubectl logs -n testing sts/sts-db-camellia
```

NodePort của `StatefulSet` service:

- Redis proxy: `30380`
- Console/metrics: `30379`

Nếu cần port-forward thay vì dùng NodePort:

```bash
kubectl port-forward -n testing svc/svc-db-camellia 6380:6380 16379:16379
```

## 6.1 Chạy proxy bằng Standalone Deployment

Overlay này tạo một proxy riêng dùng profile `standalone` (`application-standalone.yml`).

Apply:

```bash
kubectl apply -n testing -k ./deployment/standalone
```

Kiểm tra:

```bash
kubectl get deploy,pods,svc -n testing | grep standalone
kubectl rollout status deployment/deploy-camellia-proxy-standalone -n testing
```

NodePort của `Standalone` service:

- Redis proxy: `30581`
- Console/metrics: `30582`

Test nhanh:

```bash
redis-cli -h <node-ip> -p 30581 -a camellia_admin_pass PING
```

Benchmark từ benchmark pod:

```bash
kubectl exec -n testing "$BENCH_POD" -- \
  redis-benchmark -h svc-camellia-proxy-standalone -p 6380 -a camellia_admin_pass -t set,get -n 100000 -c 100 -P 32 -r 100000 -d 32
```

## 7. Test nhanh

Sau khi port-forward hoặc expose NodePort, test Redis protocol qua proxy:

```bash
redis-cli -h 127.0.0.1 -p 6380 PING
```

Ghi/đọc key:

```bash
redis-cli -h 127.0.0.1 -p 6380 SET demo:key hello
redis-cli -h 127.0.0.1 -p 6380 GET demo:key
```

Xem metrics:

```bash
curl -s http://127.0.0.1:16379/prometheus | head -n 30
```

Nếu dùng NodePort, thay `127.0.0.1` bằng IP của node.

## 8. Deploy benchmark client

Apply benchmark client:

```bash
kubectl apply -n testing -k ./benchmark
```

Kiểm tra pod:

```bash
kubectl get deploy,pods -n testing -l app=redis-benchmark-client
kubectl rollout status deployment/redis-benchmark-client -n testing
```

Lấy tên pod:

```bash
BENCH_POD="$(kubectl get pod -n testing -l app=redis-benchmark-client -o jsonpath='{.items[0].metadata.name}')"
echo "$BENCH_POD"
```

Xem biến môi trường có sẵn trong benchmark pod:

```bash
kubectl exec -n testing "$BENCH_POD" -- env | grep REDIS_BENCHMARK
```

Test kết nối từ trong cluster qua Service DNS:

```bash
kubectl exec -n testing "$BENCH_POD" -- redis-cli -h svc-camellia-proxy-cluster -p 6380 PING
```

Test kết nối qua NodePort nội bộ cluster:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-cli -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" PING'
```

Chạy benchmark nhanh qua Service DNS:

```bash
kubectl exec -n testing "$BENCH_POD" -- \
  redis-benchmark -h svc-camellia-proxy-cluster -p 6380 -n 100000 -c 100 -P 32 -r 100000 -d 64 -t set,get
```

Chạy benchmark nhanh qua NodePort nội bộ cluster:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" -n 100000 -c 100 -P 32 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'
```

Warmup trước rồi benchmark chính qua NodePort:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" -n 20000 -c 50 -P 16 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'

kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" -n 300000 -c 100 -P 32 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'
```

Nếu cần benchmark qua `StatefulSet` service thì thay host:

```bash
svc-db-camellia
```

Nếu cần benchmark qua NodePort của `StatefulSet` thì dùng:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_STS_NODEPORT_PORT" -n 100000 -c 100 -P 32 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'
```

Lưu ý:

- Benchmark qua `svc-camellia-proxy-cluster:6380` là đường đi nội bộ cluster thông thường.
- Benchmark qua `status.hostIP:30480` sẽ đi qua đường `NodePort`, phù hợp khi muốn test thêm lớp kube-proxy/NodePort.

## 9. Kiểm tra route xuống Redis backend

Vì proxy đang route theo sharding, key khác nhau có thể vào backend khác nhau.

Bạn có thể kiểm tra giá trị trực tiếp từng Redis backend:

```bash
kubectl exec -n testing deploy/redis-pool-1 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-2 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-3 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-4 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-5 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-6 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-7 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-8 -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-9 -- redis-cli KEYS '*'
```

Hoặc exec vào từng Redis rồi đọc key cụ thể:

```bash
kubectl exec -n testing deploy/redis-pool-1 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-2 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-3 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-4 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-5 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-6 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-7 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-8 -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-9 -- redis-cli GET demo:key
```

## 10. Thứ tự deploy khuyến nghị

Cho `Deployment`:

```bash
kubectl apply -n testing -k ./deployment/cluster
kubectl apply -n testing -k ./monitoring
kubectl apply -n testing -k ./benchmark
```

Cho `Standalone`:

```bash
kubectl apply -n testing -k ./deployment/standalone
kubectl apply -n testing -k ./monitoring
kubectl apply -n testing -k ./benchmark
```

Cho `StatefulSet`:

```bash
kubectl apply -n testing -k ./statefulset
kubectl apply -n testing -k ./monitoring
```

Khuyến nghị:

- Mặc định dùng `deployment/cluster` (`application-cluster.yml`)
- Dùng `deployment/standalone` (`application-standalone.yml`) khi muốn test profile standalone
- Không nên apply cả `StatefulSet` và `Deployment` cùng lúc trừ khi có chủ đích test cả hai topology

## 11. Update config

Khi sửa file trong `base/`, apply lại overlay bạn đang dùng.

Nếu đang chạy topology mặc định:

```bash
kubectl apply -n testing -k ./deployment/cluster
```

Sau đó restart proxy để nạp config mới.

`Deployment`:

```bash
kubectl apply -n testing -k ./deployment/cluster
kubectl rollout restart deployment/deploy-camellia-proxy-cluster -n testing
```

`StatefulSet`:

```bash
kubectl apply -n testing -k ./statefulset
kubectl rollout restart statefulset/sts-db-camellia -n testing
```

`Standalone`:

```bash
kubectl apply -n testing -k ./deployment/standalone
kubectl rollout restart deployment/deploy-camellia-proxy-standalone -n testing
```

## 12. Monitoring

Proxy expose metrics qua console port `16379` tại endpoint:

```text
/prometheus
```

Annotation trong Service đã đặt:

- `prometheus.io/scrape: "true"`
- `prometheus.io/port: "16379"`
- `prometheus.io/path: "/prometheus"`

Ngoài annotation, repo này đã có sẵn `ServiceMonitor` tại `monitoring/camellia-proxy-servicemonitor.yaml`.

Apply:

```bash
kubectl apply -n testing -k ./monitoring
```

Kiểm tra:

```bash
kubectl get servicemonitor -n testing
kubectl describe servicemonitor camellia-proxy -n testing
```

`ServiceMonitor` sẽ scrape mọi service có label:

- `monitoring.camellia.io/enabled=true`

Đồng thời nó copy label `camellia_topology` từ `Service` vào metric samples, nên có thể phân biệt:

- `camellia_topology="cluster"`
- `camellia_topology="standalone"`

Ví dụ query:

```promql
sum(redis_proxy_connect_count) by (camellia_topology)
sum(rate(redis_proxy_total{type="all"}[1m])) by (camellia_topology)
```

Redis backend cũng có thêm sidecar `redis_exporter`:

- image: `oliver006/redis_exporter:v1.67.0`
- metrics port: `9121`
- service label: `monitoring.redis.io/enabled=true`

`ServiceMonitor` backend:

- `learning/labs/camellia-redis/k8s/monitoring/redis-backend-servicemonitor.yaml`

Metric sẽ có thêm label:

- `redis_backend="redis-pool-1"... "redis-pool-9"`

Ví dụ query:

```promql
sum(redis_up) by (redis_backend)
sum(rate(redis_commands_processed_total[1m])) by (redis_backend)
max(redis_memory_used_bytes) by (redis_backend)
```

Dashboard Redis backend đã được thêm sẵn:

- JSON import tay: `learning/labs/camellia-redis/k8s/grafana/redis-backend-dashboard.json`
- `ConfigMap` sidecar import: `learning/labs/camellia-redis/k8s/grafana/redis-backend-dashboard-configmap.yaml`

Dashboard này đã sửa từ mẫu Redis Exporter để dùng label thực tế của lab:

- variable `redis_backend` lấy từ `label_values(redis_up, redis_backend)`
- variable `instance` lấy từ `label_values(redis_up{redis_backend=~"$redis_backend"}, instance)`

Nếu Grafana trong cluster có sidecar watch `ConfigMap` label `grafana_dashboard=1`, apply:

```bash
kubectl apply -n monitoring -k ./grafana
```

Nếu không dùng sidecar, import file JSON bằng tay trong UI Grafana.

Nếu Prometheus Operator trong cluster chỉ watch `ServiceMonitor` theo label riêng, cần thêm label bổ sung vào cả:

- `monitoring/camellia-proxy-servicemonitor.yaml`
- `monitoring/redis-backend-servicemonitor.yaml`

Ví dụ:

- `release: kube-prometheus-stack`

## 13. Traffic distribution

Cả hai service proxy đều set:

- `sessionAffinity: None`

Nghĩa là Kubernetes Service không sticky client theo `ClientIP`.

Tuy nhiên cần hiểu đúng cơ chế chia tải:

- `kube-proxy` cân bằng tải ở mức TCP connection, không cân bằng theo từng lệnh Redis như `GET` hay `SET`
- Một Redis connection đã vào pod nào thì sẽ giữ pod đó trong suốt vòng đời connection
- Nếu ứng dụng mở ít connection và giữ lâu, traffic có thể lệch giữa các pod
- Nếu ứng dụng mở nhiều connection song song, phân phối sẽ đều hơn

Kiểm tra service đang nhìn thấy bao nhiêu pod:

```bash
kubectl get endpoints -n testing svc-db-camellia
kubectl get endpoints -n testing svc-camellia-proxy-cluster
```

Nếu `StatefulSet` scale lên 2 pod:

```bash
kubectl scale statefulset sts-db-camellia -n testing --replicas=2
kubectl get pods -n testing -l app=camellia-proxy-sts
kubectl get endpoints -n testing svc-db-camellia
```

Để traffic đều hơn trong thực tế:

- Tăng số connection từ client hoặc connection pool
- Tăng số worker/client song song
- Tránh chỉ dùng 1 connection Redis lâu sống
- Nếu cần control L4 tốt hơn, dùng thêm HAProxy/Envoy/LoadBalancer phía trước Service

## 14. Troubleshooting

Proxy không lên:

```bash
kubectl describe pod -n testing <pod-name>
kubectl logs -n testing <pod-name>
```

Service không route vào pod:

```bash
kubectl get endpoints -n testing svc-db-camellia
kubectl get endpoints -n testing svc-camellia-proxy-cluster
```

Redis backend không reachable:

```bash
kubectl exec -it -n testing <proxy-pod> -- sh
```

Trong pod proxy:

```bash
nc -vz redis-pool-1 6379
nc -vz redis-pool-2 6379
nc -vz redis-pool-3 6379
nc -vz redis-pool-4 6379
nc -vz redis-pool-5 6379
nc -vz redis-pool-6 6379
nc -vz redis-pool-7 6379
nc -vz redis-pool-8 6379
nc -vz redis-pool-9 6379
```

Không có metrics:

```bash
curl -s http://<node-ip>:30379/prometheus | head
curl -s http://<node-ip>:30479/prometheus | head
kubectl logs -n testing deploy/redis-pool-1 -c redis-exporter --tail=50
kubectl exec -n testing deploy/redis-pool-1 -c redis-exporter -- wget -qO- http://127.0.0.1:9121/metrics | head
```

Benchmark client không lên:

```bash
kubectl describe deployment redis-benchmark-client -n testing
kubectl logs -n testing deploy/redis-benchmark-client
```

## 15. Cleanup

Xoá topology `StatefulSet`:

```bash
kubectl delete -n testing -k ./statefulset
```

Xoá topology `Deployment`:

```bash
kubectl delete -n testing -k ./deployment/cluster
```

Xoá topology `Standalone`:

```bash
kubectl delete -n testing -k ./deployment/standalone
```

Xoá benchmark client:

```bash
kubectl delete -n testing -k ./benchmark
```

Xoá `ServiceMonitor`:

```bash
kubectl delete -n testing -k ./monitoring
```

Xoá dashboard Redis backend trong Grafana:

```bash
kubectl delete -n monitoring -k ./grafana
```

Xoá base resources:

```bash
kubectl delete -n testing -k ./base
```
