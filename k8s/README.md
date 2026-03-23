# Camellia Redis Proxy on Kubernetes

README nay mo ta cach deploy bo manifest trong thu muc `k8s/` theo huong tham chieu docs Camellia Redis Proxy `1.3.7`.

Layout da duoc quy hoach lai de de doc hon:

- Proxy chay tren Kubernetes
- Redis backend cung chay tren Kubernetes
- Route config dung `local + resource-table.json`
- Monitoring expose qua console HTTP `/prometheus`

Topology mac dinh khuyen nghi:

- `Deployment + NodePort Service`
- scale ngang nhieu pod Camellia proxy de service phan phoi connection vao cac pod
- phu hop hon `StatefulSet` cho lab nay vi proxy dang stateless theo `ConfigMap`

Luu y quan trong:

- Bo manifest nay dang theo mo hinh `sharding local transpond`, khong phai mo hinh `multi_tenants_v1` trong lab Docker Compose.
- Nghia la proxy route theo `resource-table.json`, khong route theo password tenant.
- Neu muon multi-tenant giong Docker lab, can doi lai config proxy sang mode `route.conf.provider=multi_tenants_v1`.

## 1. Cau truc thu muc

```text
k8s/
├── README.md
├── base/
│   ├── camellia-proxy-configmap.yaml
│   ├── redis-backends.yaml
│   └── kustomization.yaml
├── statefulset/
│   ├── camellia-proxy-statefulset.yaml
│   ├── camellia-proxy-service.yaml
│   └── kustomization.yaml
└── deployment/
    ├── camellia-proxy-deployment.yaml
    ├── camellia-proxy-service.yaml
    └── kustomization.yaml
```

Y nghia:

- `base/`: tai nguyen dung chung, gom ConfigMap va 3 Redis backend
- `statefulset/`: topology proxy 1 replica
- `deployment/`: topology proxy scale-out nhieu replica

Ten file moi duoc doi theo vai tro de nhin vao la biet dung de lam gi.

## 1.1 Kustomization

Moi thu muc `base/`, `statefulset/`, `deployment/` deu co file `kustomization.yaml`.

Vai tro:

- `base/kustomization.yaml`: gom `camellia-proxy-configmap.yaml` va `redis-backends.yaml`
- `statefulset/kustomization.yaml`: include `../base` + proxy `StatefulSet` + service cua `StatefulSet`
- `deployment/kustomization.yaml`: include `../base` + proxy `Deployment` + service cua `Deployment`

Lenh chay chinh:

```bash
cd /mnt/c/Users/quyetmv/workspace-pc/learning/labs/camellia-redis/k8s
kubectl apply -n testing -k ./base
kubectl apply -n testing -k ./statefulset
kubectl apply -n testing -k ./deployment
```

Neu chi muon xem YAML sau khi render boi Kustomize:

```bash
kubectl kustomize ./base
kubectl kustomize ./statefulset
kubectl kustomize ./deployment
```

Neu may da cai binary `kustomize` rieng:

```bash
kustomize build ./base
kustomize build ./statefulset
kustomize build ./deployment
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
                    | - resource-table.json                |
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
          +--------------------------+--------------------------+
          |                          |                          |
          v                          v                          v
 +------------------+      +------------------+      +------------------+
 | redis-pool-a     |      | redis-pool-b     |      | redis-pool-c     |
 | Deployment x1    |      | Deployment x1    |      | Deployment x1    |
 | Service :6379    |      | Service :6379    |      | Service :6379    |
 +------------------+      +------------------+      +------------------+

Metrics endpoint:
  http://<proxy-host>:16379/prometheus
```

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

Trong `resource-table.json`, proxy dang dung sharding voi `bucketSize=3`:

- bucket `0` -> `redis-pool-a`
- bucket `1` -> `redis-pool-b`
- bucket `2` -> `redis-pool-c`

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
- `redis-pool-a`
- `redis-pool-b`
- `redis-pool-c`

Apply:

```bash
kubectl apply -n testing -k ./base
```

Kiem tra:

```bash
kubectl get configmap -n testing cm-db-camellia
kubectl get pods -n testing -l app=redis-pool-a
kubectl get pods -n testing -l app=redis-pool-b
kubectl get pods -n testing -l app=redis-pool-c
kubectl get svc -n testing | grep redis-pool
```

Rollout status:

```bash
kubectl rollout status deployment/redis-pool-a -n testing
kubectl rollout status deployment/redis-pool-b -n testing
kubectl rollout status deployment/redis-pool-c -n testing
```

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

## 8. Kiem tra route xuong Redis backend

Vi proxy dang route theo sharding, key khac nhau co the vao backend khac nhau.

Ban co the kiem tra gia tri truc tiep tung Redis backend:

```bash
kubectl exec -n testing deploy/redis-pool-a -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-b -- redis-cli KEYS '*'
kubectl exec -n testing deploy/redis-pool-c -- redis-cli KEYS '*'
```

Hoac exec vao tung Redis roi doc key cu the:

```bash
kubectl exec -n testing deploy/redis-pool-a -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-b -- redis-cli GET demo:key
kubectl exec -n testing deploy/redis-pool-c -- redis-cli GET demo:key
```

## 9. Thu tu deploy khuyen nghi

Cho `Deployment`:

```bash
kubectl apply -n testing -k ./deployment
```

Cho `StatefulSet`:

```bash
kubectl apply -n testing -k ./statefulset
```

Khuyen nghi:

- mac dinh dung `Deployment`
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

## 11. Monitoring

Proxy expose metrics qua console port `16379` tai endpoint:

```text
/prometheus
```

Annotation trong Service da dat:

- `prometheus.io/scrape: "true"`
- `prometheus.io/port: "16379"`
- `prometheus.io/path: "/prometheus"`

Neu cluster co Prometheus operator hoac service discovery rieng, ban co the doi sang `ServiceMonitor` sau.

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
nc -vz redis-pool-a 6379
nc -vz redis-pool-b 6379
nc -vz redis-pool-c 6379
```

Khong co metrics:

```bash
curl -s http://<node-ip>:30379/prometheus | head
curl -s http://<node-ip>:30479/prometheus | head
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

Xoa base resources:

```bash
kubectl delete -n testing -k ./base
```
