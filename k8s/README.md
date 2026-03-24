# Camellia Redis Proxy on Kubernetes

README nay mo ta cach deploy bo manifest trong thu muc `k8s/` theo huong tham chieu docs Camellia Redis Proxy `1.3.7`.

Layout da duoc quy hoach lai de de doc hon:

- Proxy chay tren Kubernetes
- Redis backend cung chay tren Kubernetes
- Route config dung `local + resource-sharding-singlewrite-multiread.json`
- Monitoring expose qua console HTTP `/prometheus`

Topology mac dinh khuyen nghi:

- `Deployment + NodePort Service`
- scale ngang nhieu pod Camellia proxy de service phan phoi connection vao cac pod
- phu hop hon `StatefulSet` cho lab nay vi proxy dang stateless theo `ConfigMap`

Luu y quan trong:

- Bo manifest nay dang theo mo hinh `sharding local transpond`, khong phai mo hinh `multi_tenants_v1` trong lab Docker Compose.
- Nghia la proxy route theo `resource-sharding-singlewrite-multiread.json`, khong route theo password tenant.
- Neu muon multi-tenant giong Docker lab, can doi lai config proxy sang mode `route.conf.provider=multi_tenants_v1`.

## 1. Cau truc thu muc

```text
k8s/
├── README.md
├── base/
│   ├── camellia-proxy-configmap.yaml
│   ├── redis-backends.yaml
│   └── kustomization.yaml
├── monitoring/
│   ├── camellia-proxy-servicemonitor.yaml
│   └── kustomization.yaml
├── statefulset/
│   ├── camellia-proxy-statefulset.yaml
│   ├── camellia-proxy-service.yaml
│   └── kustomization.yaml
├── standalone/
│   ├── camellia-proxy-standalone-deployment.yaml
│   ├── camellia-proxy-standalone-service.yaml
│   └── kustomization.yaml
├── benchmark/
│   ├── redis-benchmark-client-deployment.yaml
│   └── kustomization.yaml
└── deployment/
    ├── camellia-proxy-deployment.yaml
    ├── camellia-proxy-service.yaml
    └── kustomization.yaml
```

Y nghia:

- `base/`: tai nguyen dung chung, gom ConfigMap va 9 Redis backend
- `monitoring/`: `ServiceMonitor` de Prometheus Operator scrape metrics tu Camellia proxy
- `statefulset/`: topology proxy 1 replica
- `standalone/`: 1 proxy deployment dung config standalone, phu hop de benchmark khong bi `MOVED`
- `benchmark/`: benchmark client pod de chay `redis-benchmark` trong cluster
- `deployment/`: topology proxy scale-out nhieu replica

Ten file moi duoc doi theo vai tro de nhin vao la biet dung de lam gi.

## 1.1 Kustomization

Moi thu muc `base/`, `monitoring/`, `statefulset/`, `standalone/`, `deployment/`, `benchmark/` deu co file `kustomization.yaml`.

Vai tro:

- `base/kustomization.yaml`: gom `camellia-proxy-configmap.yaml` va `redis-backends.yaml`
- `monitoring/kustomization.yaml`: gom `camellia-proxy-servicemonitor.yaml`
- `statefulset/kustomization.yaml`: include `../base` + proxy `StatefulSet` + service cua `StatefulSet`
- `standalone/kustomization.yaml`: include `../base` + proxy `Deployment` dung `application-standalone.yml`
- `deployment/kustomization.yaml`: include `../base` + proxy `Deployment` + service cua `Deployment`
- `benchmark/kustomization.yaml`: tao 1 pod client de chay `redis-benchmark`

Lenh chay chinh:

```bash
cd /mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis/k8s
kubectl apply -n testing -k ./base
kubectl apply -n testing -k ./monitoring
kubectl apply -n testing -k ./statefulset
kubectl apply -n testing -k ./standalone
kubectl apply -n testing -k ./deployment
kubectl apply -n testing -k ./benchmark
```

Neu chi muon xem YAML sau khi render boi Kustomize:

```bash
kubectl kustomize ./base
kubectl kustomize ./monitoring
kubectl kustomize ./statefulset
kubectl kustomize ./standalone
kubectl kustomize ./deployment
kubectl kustomize ./benchmark
```

Neu may da cai binary `kustomize` rieng:

```bash
kustomize build ./base
kustomize build ./monitoring
kustomize build ./statefulset
kustomize build ./standalone
kustomize build ./deployment
kustomize build ./benchmark
```

Ban chi nen chon 1 trong 2 cach chay proxy:

1. `Deployment`: topology mac dinh, de scale-out va can bang tai
2. `StatefulSet`: topology tuy chon, chi dung khi ban can test semantic cua StatefulSet

## 2. Topology

```text
                          +----------------------+
                          |      client app      |
                          | redis-cli / service  |
                          +----------+-----------+
                                     |
                                     v
                    +----------------------------------+
                    | svc-db-camellia-deploy          |
                    | NodePort 30480                  |
                    | console 30479                   |
                    +----------------+-----------------+
                                     |
                                     v
                    +----------------------------------+
                    | Deployment proxy                 |
                    | deploy-db-camellia              |
                    | replicas = 3                    |
                    | pod labels:                     |
                    |   app=camellia-proxy-deploy     |
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
                    | Camellia local transpond            |
                    | type=complex, json-file=resource-   |
                    | table.json, bucketSize=3            |
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

Neu cluster dung Prometheus Operator hoac `kube-prometheus-stack`, co the them `ServiceMonitor` de scrape metrics qua service port `console`.

Topology tuy chon `StatefulSet`:

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

Trong `resource-sharding-singlewrite-multiread.json`, proxy dang dung sharding `bucketSize=3` voi `single write / multiple read`:

- bucket `0`: write `redis-pool-1`, read random tu `redis-pool-2`, `redis-pool-3`
- bucket `1`: write `redis-pool-4`, read random tu `redis-pool-5`, `redis-pool-6`
- bucket `2`: write `redis-pool-7`, read random tu `redis-pool-8`, `redis-pool-9`

## 3. Preconditions

Can co:

- `kubectl`
- mot cluster Kubernetes dang truy cap duoc
- namespace deploy, vi du `testing`

Kiem tra context hien tai:

```bash
cd /mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis/k8s
kubectl config current-context
kubectl get ns
```

Tao namespace neu chua co:

```bash
kubectl create namespace testing
```

## 4. Deploy base resources

`base/` gom:

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

Kiem tra:

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

Phan nay chi can khi cluster da co CRD `ServiceMonitor` va co Prometheus Operator dang watch namespace `testing`.

Kiem tra CRD:

```bash
kubectl get crd servicemonitors.monitoring.coreos.com
```

Apply:

```bash
kubectl apply -n testing -k ./monitoring
```

Kiem tra:

```bash
kubectl get servicemonitor -n testing
kubectl describe servicemonitor camellia-proxy -n testing
```

ServiceMonitor nay se scrape moi service Camellia proxy co label:

- `monitoring.camellia.io/enabled=true`

Hien tai da gan label nay cho ca:

- `svc-db-camellia-deploy`
- `svc-db-camellia`

Endpoint scrape:

- port: `console`
- path: `/prometheus`
- interval: `15s`

Luu y:

- Neu dung `kube-prometheus-stack`, Prometheus instance cua ban co the chi select `ServiceMonitor` co them label nhu `release: kube-prometheus-stack`.
- Neu gap truong hop do, patch them label vao file `monitoring/camellia-proxy-servicemonitor.yaml` cho khop selector cua Prometheus trong cluster.

## 5. Chay proxy bang Deployment

Day la topology mac dinh nen dung cho lab nay.

Ly do:

- Camellia proxy trong lab dang stateless theo `ConfigMap`
- can scale ngang nhieu pod de `Service` phan phoi connection
- khong can stable identity cua `StatefulSet`

Apply:

```bash
kubectl apply -n testing -k ./deployment
```

Kiem tra:

```bash
kubectl get deploy,pods,svc -n testing | grep camellia
kubectl rollout status deployment/deploy-db-camellia -n testing
```

Scale them neu can:

```bash
kubectl scale deployment deploy-db-camellia -n testing --replicas=6
```

NodePort cua `Deployment` service:

- Redis proxy: `30480`
- Console/metrics: `30479`

Port-forward:

```bash
kubectl port-forward -n testing svc/svc-db-camellia-deploy 6380:6380 16379:16379
```

## 6. Chay proxy bang StatefulSet

Day la topology tuy chon. Chi dung khi ban muon test behavior cua `StatefulSet`.

Apply:

```bash
kubectl apply -n testing -k ./statefulset
```

Kiem tra:

```bash
kubectl get sts,pods,svc -n testing | grep camellia
kubectl rollout status statefulset/sts-db-camellia -n testing
```

Logs:

```bash
kubectl logs -n testing sts/sts-db-camellia
```

NodePort cua `StatefulSet` service:

- Redis proxy: `30380`
- Console/metrics: `30379`

Neu can port-forward thay vi dung NodePort:

```bash
kubectl port-forward -n testing svc/svc-db-camellia 6380:6380 16379:16379
```

## 6.1 Chay proxy bang Standalone Deployment

Overlay nay tao mot proxy rieng de benchmark theo mode standalone, tranh redirect `MOVED`.

Apply:

```bash
kubectl apply -n testing -k ./standalone
```

Kiem tra:

```bash
kubectl get deploy,pods,svc -n testing | grep standalone
kubectl rollout status deployment/deploy-db-camellia-standalone -n testing
```

NodePort cua `Standalone` service:

- Redis proxy: `30580`
- Console/metrics: `30579`

Test nhanh:

```bash
redis-cli -h <node-ip> -p 30580 -a camellia_admin_pass PING
```

Benchmark tu benchmark pod:

```bash
kubectl exec -n testing "$BENCH_POD" -- \
  redis-benchmark -h svc-db-camellia-standalone -p 6380 -a camellia_admin_pass -t set,get -n 100000 -c 100 -P 32 -r 100000 -d 32
```

## 7. Test nhanh

Sau khi port-forward hoac expose NodePort, test Redis protocol qua proxy:

```bash
redis-cli -h 127.0.0.1 -p 6380 PING
```

Ghi doc key:

```bash
redis-cli -h 127.0.0.1 -p 6380 SET demo:key hello
redis-cli -h 127.0.0.1 -p 6380 GET demo:key
```

Xem metrics:

```bash
curl -s http://127.0.0.1:16379/prometheus | head -n 30
```

Neu dung NodePort, thay `127.0.0.1` bang IP cua node.

## 8. Deploy benchmark client

Apply benchmark client:

```bash
kubectl apply -n testing -k ./benchmark
```

Kiem tra pod:

```bash
kubectl get deploy,pods -n testing -l app=redis-benchmark-client
kubectl rollout status deployment/redis-benchmark-client -n testing
```

Lay ten pod:

```bash
BENCH_POD="$(kubectl get pod -n testing -l app=redis-benchmark-client -o jsonpath='{.items[0].metadata.name}')"
echo "$BENCH_POD"
```

Xem bien moi truong co san trong benchmark pod:

```bash
kubectl exec -n testing "$BENCH_POD" -- env | grep REDIS_BENCHMARK
```

Test ket noi tu trong cluster qua Service DNS:

```bash
kubectl exec -n testing "$BENCH_POD" -- redis-cli -h svc-db-camellia-deploy -p 6380 PING
```

Test ket noi qua NodePort noi bo cluster:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-cli -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" PING'
```

Chay benchmark nhanh qua Service DNS:

```bash
kubectl exec -n testing "$BENCH_POD" -- \
  redis-benchmark -h svc-db-camellia-deploy -p 6380 -n 100000 -c 100 -P 32 -r 100000 -d 64 -t set,get
```

Chay benchmark nhanh qua NodePort noi bo cluster:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" -n 100000 -c 100 -P 32 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'
```

Warmup truoc roi benchmark chinh qua NodePort:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" -n 20000 -c 50 -P 16 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'

kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_DEPLOY_NODEPORT_PORT" -n 300000 -c 100 -P 32 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'
```

Neu can benchmark qua `StatefulSet` service thi thay host:

```bash
svc-db-camellia
```

Neu can benchmark qua NodePort cua `StatefulSet` thi dung:

```bash
kubectl exec -n testing "$BENCH_POD" -- sh -c 'redis-benchmark -h "$REDIS_BENCHMARK_NODEPORT_HOST" -p "$REDIS_BENCHMARK_STS_NODEPORT_PORT" -n 100000 -c 100 -P 32 -r "$REDIS_BENCHMARK_KEYSPACE" -d "$REDIS_BENCHMARK_DATA_SIZE" -t set,get'
```

Luu y:

- Benchmark qua `svc-db-camellia-deploy:6380` la duong di noi bo cluster thong thuong.
- Benchmark qua `status.hostIP:30480` se di qua duong `NodePort`, phu hop khi ban muon test them lop kube-proxy/NodePort.

## 9. Kiem tra route xuong Redis backend

Vi proxy dang route theo sharding, key khac nhau co the vao backend khac nhau.

Ban co the kiem tra gia tri truc tiep tung Redis backend:

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

Hoac exec vao tung Redis roi doc key cu the:

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

## 10. Thu tu deploy khuyen nghi

Cho `Deployment`:

```bash
kubectl apply -n testing -k ./deployment
kubectl apply -n testing -k ./monitoring
kubectl apply -n testing -k ./benchmark
```

Cho `Standalone`:

```bash
kubectl apply -n testing -k ./standalone
kubectl apply -n testing -k ./monitoring
kubectl apply -n testing -k ./benchmark
```

Cho `StatefulSet`:

```bash
kubectl apply -n testing -k ./statefulset
kubectl apply -n testing -k ./monitoring
```

Khuyen nghi:

- mac dinh dung `Deployment`
- dung `standalone/` khi muon benchmark mot endpoint non-cluster, khong bi `MOVED`
- khong nen apply ca `StatefulSet` va `Deployment` cung luc tru khi ban co chu dich test ca hai topology

## 10. Update config

Khi sua file trong `base/`, apply lai overlay ban dang dung.

Neu ban dang chay topology mac dinh:

```bash
kubectl apply -n testing -k ./deployment
```

Sau do restart proxy de nap config moi:

`Deployment`:

```bash
kubectl apply -n testing -k ./deployment
kubectl rollout restart deployment/deploy-db-camellia -n testing
```

`StatefulSet`:

```bash
kubectl apply -n testing -k ./statefulset
kubectl rollout restart statefulset/sts-db-camellia -n testing
```

`Standalone`:

```bash
kubectl apply -n testing -k ./standalone
kubectl rollout restart deployment/deploy-db-camellia-standalone -n testing
```

## 11. Monitoring

Proxy expose metrics qua console port `16379` tai endpoint:

```text
/prometheus
```

Annotation trong Service da dat:

- `prometheus.io/scrape: "true"`
- `prometheus.io/port: "16379"`
- `prometheus.io/path: "/prometheus"`

Ngoai annotation, repo nay da co san `ServiceMonitor` tai `monitoring/camellia-proxy-servicemonitor.yaml`.

Apply:

```bash
kubectl apply -n testing -k ./monitoring
```

Kiem tra:

```bash
kubectl get servicemonitor -n testing
kubectl describe servicemonitor camellia-proxy -n testing
```

`ServiceMonitor` se scrape moi service co label:

- `monitoring.camellia.io/enabled=true`

Neu Prometheus Operator trong cluster cua ban chi watch `ServiceMonitor` theo label rieng, can them label bo sung vao file `monitoring/camellia-proxy-servicemonitor.yaml`, vi du:

- `release: kube-prometheus-stack`

## 12. Traffic distribution

Ca hai service proxy deu set:

- `sessionAffinity: None`

Nghia la Kubernetes Service khong sticky client theo `ClientIP`.

Tuy nhien can hieu dung co che chia tai:

- `kube-proxy` can bang tai o muc TCP connection, khong can bang theo tung lenh Redis nhu `GET` hay `SET`
- mot Redis connection da vao pod nao thi se giu pod do trong suot vong doi connection
- neu ung dung mo it connection va giu lau, traffic co the lech giua cac pod
- neu ung dung mo nhieu connection song song, phan phoi se deu hon

Kiem tra service dang nhin thay bao nhieu pod:

```bash
kubectl get endpoints -n testing svc-db-camellia
kubectl get endpoints -n testing svc-db-camellia-deploy
```

Neu `StatefulSet` scale len 2 pod:

```bash
kubectl scale statefulset sts-db-camellia -n testing --replicas=2
kubectl get pods -n testing -l app=camellia-proxy-sts
kubectl get endpoints -n testing svc-db-camellia
```

De traffic deu hon trong thuc te:

- tang so connection tu client hoac connection pool
- tang so worker/client song song
- tranh chi dung 1 connection Redis lau song
- neu can control L4 tot hon, dung them HAProxy/Envoy/LoadBalancer phia truoc Service

## 13. Troubleshooting

Proxy khong len:

```bash
kubectl describe pod -n testing <pod-name>
kubectl logs -n testing <pod-name>
```

Service khong route vao pod:

```bash
kubectl get endpoints -n testing svc-db-camellia
kubectl get endpoints -n testing svc-db-camellia-deploy
```

Redis backend khong reachable:

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

Khong co metrics:

```bash
curl -s http://<node-ip>:30379/prometheus | head
curl -s http://<node-ip>:30479/prometheus | head
```

Benchmark client khong len:

```bash
kubectl describe deployment redis-benchmark-client -n testing
kubectl logs -n testing deploy/redis-benchmark-client
```

## 14. Cleanup

Xoa topology `StatefulSet`:

```bash
kubectl delete -n testing -k ./statefulset
```

Xoa topology `Deployment`:

```bash
kubectl delete -n testing -k ./deployment
```

Xoa topology `Standalone`:

```bash
kubectl delete -n testing -k ./standalone
```

Xoa benchmark client:

```bash
kubectl delete -n testing -k ./benchmark
```

Xoa `ServiceMonitor`:

```bash
kubectl delete -n testing -k ./monitoring
```

Xoa base resources:

```bash
kubectl delete -n testing -k ./base
```
