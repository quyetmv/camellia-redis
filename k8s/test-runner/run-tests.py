import os
import random
import statistics
import string
import sys
import threading
import time
from dataclasses import dataclass, field

import redis
from redis.exceptions import ResponseError


TEST_SCENARIO = os.environ.get("TEST_SCENARIO", "cluster").lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "camellia_admin_pass")
RUN_INTERVAL_SECONDS = int(os.environ.get("RUN_INTERVAL_SECONDS", "60"))
RUN_FOREVER = os.environ.get("RUN_FOREVER", "true").lower() == "true"

STRESS_CLIENTS = int(os.environ.get("STRESS_CLIENTS", "24"))
STRESS_REQUESTS_PER_CLIENT = int(os.environ.get("STRESS_REQUESTS_PER_CLIENT", "2000"))
SET_PERCENT = int(os.environ.get("SET_PERCENT", "30"))
GET_PERCENT = int(os.environ.get("GET_PERCENT", "70"))
HOT_KEY_PERCENT = int(os.environ.get("HOT_KEY_PERCENT", "20"))
HOT_KEY_COUNT = int(os.environ.get("HOT_KEY_COUNT", "8"))
KEYSPACE = int(os.environ.get("KEYSPACE", "50000"))
VALUE_SIZE = int(os.environ.get("VALUE_SIZE", "128"))
REPORT_EVERY = int(os.environ.get("REPORT_EVERY", "500"))
SCENARIO_DELAY_SECONDS = int(os.environ.get("SCENARIO_DELAY_SECONDS", "3"))

ORDER_SERVICE_PREFIX = os.environ.get("ORDER_SERVICE_PREFIX", "svc:order")
PAYMENT_SERVICE_PREFIX = os.environ.get("PAYMENT_SERVICE_PREFIX", "svc:payment")
SEARCH_SERVICE_PREFIX = os.environ.get("SEARCH_SERVICE_PREFIX", "svc:search")
ORDER_PASSWORD = os.environ.get("ORDER_PASSWORD", "svcOrderPwd")
PAYMENT_PASSWORD = os.environ.get("PAYMENT_PASSWORD", "svcPaymentPwd")
SEARCH_PASSWORD = os.environ.get("SEARCH_PASSWORD", "svcSearchPwd")

REDIS_CLIENT_KWARGS = {
    "decode_responses": True,
    "lib_name": None,
    "lib_version": None,
}


@dataclass(frozen=True)
class ServiceTarget:
    name: str
    prefix: str
    password: str


@dataclass
class ThreadStats:
    completed: int = 0
    failures: int = 0
    set_ops: int = 0
    get_ops: int = 0
    bytes_written: int = 0
    bytes_read: int = 0
    latencies_ms: list[float] = field(default_factory=list)


SERVICES = [
    ServiceTarget("order", ORDER_SERVICE_PREFIX, ORDER_PASSWORD),
    ServiceTarget("payment", PAYMENT_SERVICE_PREFIX, PAYMENT_PASSWORD),
    ServiceTarget("search", SEARCH_SERVICE_PREFIX, SEARCH_PASSWORD),
]


def _parse_moved(error_text: str) -> tuple[str, int] | None:
    if "MOVED" not in error_text:
        return None
    parts = error_text.split()
    if len(parts) < 3:
        return None
    host_port = parts[2]
    if ":" not in host_port:
        return None
    host, port = host_port.rsplit(":", 1)
    try:
        return host, int(port)
    except ValueError:
        return None


class ProxyClient:
    def __init__(self, host: str, port: int, password: str | None):
        self.host = host
        self.port = port
        self.password = password
        self.conn = self._new_conn(host, port)

    def _new_conn(self, host: str, port: int):
        return redis.Redis(host=host, port=port, password=self.password, **REDIS_CLIENT_KWARGS)

    def _retry_on_moved(self, fn):
        try:
            return fn(self.conn)
        except ResponseError as exc:
            moved = _parse_moved(str(exc))
            if not moved:
                raise
            host, port = moved
            self.host = host
            self.port = port
            self.conn = self._new_conn(host, port)
            return fn(self.conn)

    def set(self, key: str, value: str):
        return self._retry_on_moved(lambda client: client.set(key, value))

    def get(self, key: str):
        return self._retry_on_moved(lambda client: client.get(key))

    def delete(self, *keys: str):
        return self._retry_on_moved(lambda client: client.delete(*keys))

    def mget(self, keys: list[str]):
        return self._retry_on_moved(lambda client: client.mget(keys))


def get_scenarios():
    mapping = {
        "cluster": {
            "name": "cluster",
            "client_mode": "cluster",
            "key_routing_host": os.environ.get("KEY_ROUTING_HOST_CLUSTER", "svc-camellia-proxy-cluster-key-routing"),
            "shared_auth_host": os.environ.get("SHARED_AUTH_HOST_CLUSTER", "svc-camellia-proxy-cluster-shared-auth"),
            "key_routing_port": int(os.environ.get("KEY_ROUTING_PORT_CLUSTER", "6380")),
            "shared_auth_port": int(os.environ.get("SHARED_AUTH_PORT_CLUSTER", "6380")),
        },
        "standalone": {
            "name": "standalone",
            "client_mode": "standalone",
            "key_routing_host": os.environ.get("KEY_ROUTING_HOST_STANDALONE", "svc-camellia-proxy-standalone-key-routing"),
            "shared_auth_host": os.environ.get("SHARED_AUTH_HOST_STANDALONE", "svc-camellia-proxy-standalone-shared-auth"),
            "key_routing_port": int(os.environ.get("KEY_ROUTING_PORT_STANDALONE", "6380")),
            "shared_auth_port": int(os.environ.get("SHARED_AUTH_PORT_STANDALONE", "6380")),
        },
    }
    if TEST_SCENARIO == "both":
        return [mapping["cluster"], mapping["standalone"]]
    if TEST_SCENARIO in mapping:
        return [mapping[TEST_SCENARIO]]
    return [mapping["cluster"]]


def validate_settings():
    if STRESS_CLIENTS <= 0:
        raise ValueError("STRESS_CLIENTS must be > 0")
    if STRESS_REQUESTS_PER_CLIENT <= 0:
        raise ValueError("STRESS_REQUESTS_PER_CLIENT must be > 0")
    if KEYSPACE <= 0:
        raise ValueError("KEYSPACE must be > 0")
    if VALUE_SIZE <= 0:
        raise ValueError("VALUE_SIZE must be > 0")
    if HOT_KEY_COUNT <= 0:
        raise ValueError("HOT_KEY_COUNT must be > 0")
    if SET_PERCENT < 0 or GET_PERCENT < 0 or HOT_KEY_PERCENT < 0:
        raise ValueError("SET_PERCENT, GET_PERCENT, HOT_KEY_PERCENT must be >= 0")
    if SET_PERCENT + GET_PERCENT != 100:
        raise ValueError("SET_PERCENT + GET_PERCENT must equal 100")
    if HOT_KEY_PERCENT > 100:
        raise ValueError("HOT_KEY_PERCENT must be <= 100")


def build_random_value(size: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=size))


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q)))
    return ordered[index]


def build_key(service: ServiceTarget, worker_id: int) -> str:
    if random.randint(1, 100) <= HOT_KEY_PERCENT:
        slot = random.randint(1, HOT_KEY_COUNT)
        hot_name = HOT_KEY_NAME.replace("{service}", service.name)
        return f"{service.prefix}:{hot_name}:{slot}"
    slot = random.randint(1, KEYSPACE)
    return f"{service.prefix}:worker:{worker_id}:key:{slot}"


def preflight_checks(suite: dict) -> tuple[bool, list[str]]:
    messages = []
    try:
        admin = ProxyClient(suite["key_routing_host"], suite["key_routing_port"], ADMIN_PASSWORD)
        key = f"k8s:runner:preflight:{suite['name']}:{int(time.time())}"
        admin.set(key, "ok")
        value = admin.get(key)
        admin.delete(key)
        if value != "ok":
            return False, [f"admin preflight mismatch value={value}"]
        messages.append("admin route ok")
    except Exception as exc:
        return False, [f"admin preflight error: {exc}"]

    try:
        suffix = f"preflight:{int(time.time())}"
        values = {}
        for service in SERVICES:
            client = ProxyClient(suite["shared_auth_host"], suite["shared_auth_port"], service.password)
            key = f"{service.prefix}:{suffix}"
            payload = f"{service.name}-ok"
            client.set(key, payload)
            values[service.name] = client.get(key)
            client.delete(key)
        if values != {"order": "order-ok", "payment": "payment-ok", "search": "search-ok"}:
            return False, [f"shared-auth preflight mismatch values={values}"]
        messages.append("shared-auth route ok")
    except Exception as exc:
        return False, [f"shared-auth preflight error: {exc}"]

    try:
        cluster_keys = [f"k8s:runner:{{tenant}}:{index}" for index in range(1, 4)]
        cluster_client = ProxyClient(suite["key_routing_host"], suite["key_routing_port"], ADMIN_PASSWORD)
        for index, key in enumerate(cluster_keys, start=1):
            cluster_client.set(key, f"v{index}")
        actual = cluster_client.mget(cluster_keys)
        cluster_client.delete(*cluster_keys)
        if actual != ["v1", "v2", "v3"]:
            return False, [f"multi-key preflight mismatch actual={actual}"]
        messages.append("multi-key route ok")
    except Exception as exc:
        return False, [f"multi-key preflight error: {exc}"]

    return True, messages


def worker(suite: dict, service: ServiceTarget, worker_id: int, stats: ThreadStats, barrier: threading.Barrier):
    client = ProxyClient(suite["shared_auth_host"], suite["shared_auth_port"], service.password)
    payload = build_random_value(VALUE_SIZE)
    barrier.wait()
    for index in range(STRESS_REQUESTS_PER_CLIENT):
        key = build_key(service, worker_id)
        is_set = random.randint(1, 100) <= SET_PERCENT
        started = time.perf_counter()
        try:
            if is_set:
                client.set(key, payload)
                stats.set_ops += 1
                stats.bytes_written += len(payload)
            else:
                value = client.get(key)
                stats.get_ops += 1
                if value is not None:
                    stats.bytes_read += len(value)
            stats.completed += 1
        except Exception:
            stats.failures += 1
        finally:
            stats.latencies_ms.append((time.perf_counter() - started) * 1000)

        if REPORT_EVERY > 0 and (index + 1) % REPORT_EVERY == 0:
            print(
                f"[progress] scenario={suite['name']} service={service.name} "
                f"worker={worker_id} completed={index + 1}/{STRESS_REQUESTS_PER_CLIENT}"
            )


def aggregate(thread_stats: list[ThreadStats]) -> dict:
    latencies = [lat for stat in thread_stats for lat in stat.latencies_ms]
    return {
        "completed": sum(stat.completed for stat in thread_stats),
        "failures": sum(stat.failures for stat in thread_stats),
        "set_ops": sum(stat.set_ops for stat in thread_stats),
        "get_ops": sum(stat.get_ops for stat in thread_stats),
        "bytes_written": sum(stat.bytes_written for stat in thread_stats),
        "bytes_read": sum(stat.bytes_read for stat in thread_stats),
        "latencies": latencies,
    }


def run_stress(suite: dict) -> tuple[bool, list[str]]:
    threads = []
    thread_stats = []
    barrier = threading.Barrier(STRESS_CLIENTS)

    print(
        f"[INFO] stress scenario={suite['name']} mode={suite['client_mode']} "
        f"clients={STRESS_CLIENTS} requests_per_client={STRESS_REQUESTS_PER_CLIENT} "
        f"ratio=set:{SET_PERCENT}% get:{GET_PERCENT}% hot_key={HOT_KEY_PERCENT}%/{HOT_KEY_COUNT}"
    )

    started = time.perf_counter()
    for worker_index in range(STRESS_CLIENTS):
        service = SERVICES[worker_index % len(SERVICES)]
        stats = ThreadStats()
        thread_stats.append(stats)
        thread = threading.Thread(
            target=worker,
            args=(suite, service, worker_index + 1, stats, barrier),
            daemon=True,
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started

    totals = aggregate(thread_stats)
    throughput = totals["completed"] / elapsed if elapsed > 0 else 0.0
    avg_latency = statistics.fmean(totals["latencies"]) if totals["latencies"] else 0.0
    p95 = percentile(totals["latencies"], 0.95)
    p99 = percentile(totals["latencies"], 0.99)

    summary = [
        f"completed={totals['completed']}",
        f"failures={totals['failures']}",
        f"set_ops={totals['set_ops']}",
        f"get_ops={totals['get_ops']}",
        f"elapsed_seconds={elapsed:.2f}",
        f"throughput_rps={throughput:.2f}",
        f"latency_avg_ms={avg_latency:.2f}",
        f"latency_p95_ms={p95:.2f}",
        f"latency_p99_ms={p99:.2f}",
        f"bytes_written={totals['bytes_written']}",
        f"bytes_read={totals['bytes_read']}",
    ]

    for line in summary:
        print(f"[SUMMARY] scenario={suite['name']} {line}")

    return totals["failures"] == 0, summary


def run_suite(suite: dict) -> bool:
    print("=== Camellia K8s stress-runner ===")
    print(
        f"scenario={suite['name']} mode={suite['client_mode']} "
        f"keyRouting={suite['key_routing_host']}:{suite['key_routing_port']} "
        f"sharedAuth={suite['shared_auth_host']}:{suite['shared_auth_port']}"
    )

    ok, messages = preflight_checks(suite)
    if not ok:
        for message in messages:
            print(f"[FAIL] preflight {message}")
        return False
    for message in messages:
        print(f"[PASS] preflight {message}")

    ok, _ = run_stress(suite)
    if not ok:
        print(f"[FAIL] stress scenario={suite['name']}")
        return False
    print(f"[PASS] stress scenario={suite['name']}")
    return True


def run_once() -> int:
    validate_settings()
    scenarios = get_scenarios()
    overall = True
    for index, suite in enumerate(scenarios):
        if not run_suite(suite):
            overall = False
        if index < len(scenarios) - 1 and SCENARIO_DELAY_SECONDS > 0:
            print(f"[INFO] sleeping {SCENARIO_DELAY_SECONDS}s before next scenario")
            time.sleep(SCENARIO_DELAY_SECONDS)
    return 0 if overall else 1


def main():
    if not RUN_FOREVER:
        sys.exit(run_once())

    while True:
        code = run_once()
        if code != 0:
            print(f"[WARN] One or more checks failed. Next retry in {RUN_INTERVAL_SECONDS}s.")
        time.sleep(RUN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
