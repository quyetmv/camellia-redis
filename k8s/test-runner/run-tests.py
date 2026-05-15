import os
import random
import string
import sys
import threading
import time
from dataclasses import dataclass, field

import redis
from redis.exceptions import ResponseError


TEST_SCENARIO = os.environ.get("TEST_SCENARIO", "both").lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "camellia_admin_pass")
RUN_INTERVAL_SECONDS = int(os.environ.get("RUN_INTERVAL_SECONDS", "60"))
RUN_FOREVER = os.environ.get("RUN_FOREVER", "true").lower() == "true"

STRESS_CLIENTS = int(os.environ.get("STRESS_CLIENTS", "200"))
STRESS_REQUESTS_PER_CLIENT = int(os.environ.get("STRESS_REQUESTS_PER_CLIENT", "10000"))
SET_PERCENT = int(os.environ.get("SET_PERCENT", "30"))
GET_PERCENT = int(os.environ.get("GET_PERCENT", "70"))
HOT_KEY_PERCENT = int(os.environ.get("HOT_KEY_PERCENT", "40"))
HOT_KEY_COUNT = int(os.environ.get("HOT_KEY_COUNT", "4"))
HOT_KEY_NAME = os.environ.get("HOT_KEY_NAME", "session:{service}:{hot-user}:profile")
KEYSPACE = int(os.environ.get("KEYSPACE", "200000"))
VALUE_SIZE = int(os.environ.get("VALUE_SIZE", "256"))
REPORT_EVERY = int(os.environ.get("REPORT_EVERY", "2000"))
REPORT_INTERVAL_SECONDS = int(os.environ.get("REPORT_INTERVAL_SECONDS", "5"))
SCENARIO_DELAY_SECONDS = int(os.environ.get("SCENARIO_DELAY_SECONDS", "0"))

ORDER_PASSWORD = os.environ.get("ORDER_PASSWORD", "order-service")
PAYMENT_PASSWORD = os.environ.get("PAYMENT_PASSWORD", "payment-service")
SEARCH_PASSWORD = os.environ.get("SEARCH_PASSWORD", "search-service")

REDIS_CLIENT_KWARGS = {
    "decode_responses": True,
    "lib_name": None,
    "lib_version": None,
}


@dataclass(frozen=True)
class ServiceTarget:
    name: str
    password: str


@dataclass
class ThreadStats:
    completed: int = 0
    failures: int = 0
    set_ops: int = 0
    get_ops: int = 0
    bytes_written: int = 0
    bytes_read: int = 0
    latency_count: int = 0
    latency_total_ms: float = 0.0
    latency_max_ms: float = 0.0
    latency_buckets: list[int] = field(default_factory=lambda: [0] * len(LATENCY_BUCKETS_MS))


SERVICES = [
    ServiceTarget("order", ORDER_PASSWORD),
    ServiceTarget("payment", PAYMENT_PASSWORD),
    ServiceTarget("search", SEARCH_PASSWORD),
]

LATENCY_BUCKETS_MS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
KEY_COUNTERS = {service.name: 0 for service in SERVICES}
KEY_COUNTER_LOCK = threading.Lock()


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
            "shared_auth_host": os.environ.get(
                "SHARED_AUTH_KEY_ROUTING_HOST_CLUSTER",
                "svc-camellia-proxy-cluster-shared-auth-key-routing",
            ),
            "shared_auth_port": int(os.environ.get("SHARED_AUTH_KEY_ROUTING_PORT_CLUSTER", "6380")),
            "key_routing_host": os.environ.get("KEY_ROUTING_HOST_CLUSTER", "svc-camellia-proxy-cluster-key-routing"),
            "key_routing_port": int(os.environ.get("KEY_ROUTING_PORT_CLUSTER", "6380")),
        },
        "standalone": {
            "name": "standalone",
            "shared_auth_host": os.environ.get(
                "SHARED_AUTH_KEY_ROUTING_HOST_STANDALONE",
                "svc-camellia-proxy-standalone-shared-auth-key-routing",
            ),
            "shared_auth_port": int(os.environ.get("SHARED_AUTH_KEY_ROUTING_PORT_STANDALONE", "6380")),
            "key_routing_host": os.environ.get(
                "KEY_ROUTING_HOST_STANDALONE",
                "svc-camellia-proxy-standalone-key-routing",
            ),
            "key_routing_port": int(os.environ.get("KEY_ROUTING_PORT_STANDALONE", "6380")),
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
    if "{service}" not in HOT_KEY_NAME:
        raise ValueError("HOT_KEY_NAME must contain '{service}' placeholder")


def build_random_value(size: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=size))


def record_latency(stats: ThreadStats, latency_ms: float):
    stats.latency_count += 1
    stats.latency_total_ms += latency_ms
    if latency_ms > stats.latency_max_ms:
        stats.latency_max_ms = latency_ms
    for index, upper_bound in enumerate(LATENCY_BUCKETS_MS):
        if latency_ms <= upper_bound:
            stats.latency_buckets[index] += 1
            return
    stats.latency_buckets[-1] += 1


def percentile_from_buckets(bucket_counts: list[int], q: float) -> float:
    total = sum(bucket_counts)
    if total <= 0:
        return 0.0
    target = max(1, int(total * q))
    current = 0
    for upper_bound, count in zip(LATENCY_BUCKETS_MS, bucket_counts):
        current += count
        if current >= target:
            return float(upper_bound)
    return float(LATENCY_BUCKETS_MS[-1])


def build_key(service: ServiceTarget, worker_id: int) -> str:
    with KEY_COUNTER_LOCK:
        KEY_COUNTERS[service.name] += 1
        sequence = KEY_COUNTERS[service.name]
    return f"{service.name}:key:{sequence}"


def preflight_checks(suite: dict) -> tuple[bool, list[str]]:
    messages = []

    try:
        admin = ProxyClient(suite["key_routing_host"], suite["key_routing_port"], ADMIN_PASSWORD)
        key = f"k8s:runner:admin:preflight:{suite['name']}:{int(time.time())}"
        admin.set(key, "ok")
        value = admin.get(key)
        admin.delete(key)
        if value != "ok":
            return False, [f"admin preflight mismatch value={value}"]
        messages.append("admin endpoint ok")
    except Exception as exc:
        return False, [f"admin preflight error: {exc}"]

    try:
        suffix = f"tenant-preflight:{int(time.time())}"
        values = {}
        for service in SERVICES:
            client = ProxyClient(suite["shared_auth_host"], suite["shared_auth_port"], service.password)
            key = f"{service.name}:{suffix}"
            payload = f"{service.name}-ok"
            client.set(key, payload)
            values[service.name] = client.get(key)
            client.delete(key)
        if values != {"order": "order-ok", "payment": "payment-ok", "search": "search-ok"}:
            return False, [f"tenant preflight mismatch values={values}"]
        messages.append("tenant auth route ok")
    except Exception as exc:
        return False, [f"tenant preflight error: {exc}"]

    try:
        shared_key = f"isolation:{int(time.time())}"
        order_client = ProxyClient(suite["shared_auth_host"], suite["shared_auth_port"], ORDER_PASSWORD)
        payment_client = ProxyClient(suite["shared_auth_host"], suite["shared_auth_port"], PAYMENT_PASSWORD)
        order_client.set(shared_key, "order-owned")
        order_value = order_client.get(shared_key)
        payment_value = payment_client.get(shared_key)
        order_client.delete(shared_key)
        if order_value != "order-owned" or payment_value is not None:
            return False, [f"tenant isolation mismatch order={order_value} payment={payment_value}"]
        messages.append("tenant isolation ok")
    except Exception as exc:
        return False, [f"tenant isolation error: {exc}"]

    try:
        for service in SERVICES:
            client = ProxyClient(suite["shared_auth_host"], suite["shared_auth_port"], service.password)
            keys = [f"route:{{{service.name}}}:{i}" for i in range(1, 4)]
            for index, key in enumerate(keys, start=1):
                client.set(key, f"v{index}")
            actual = client.mget(keys)
            client.delete(*keys)
            if actual != ["v1", "v2", "v3"]:
                return False, [f"key routing mismatch service={service.name} actual={actual}"]
        messages.append("key routing with hash-tag ok")
    except Exception as exc:
        return False, [f"key routing preflight error: {exc}"]

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
            record_latency(stats, (time.perf_counter() - started) * 1000)


def aggregate(thread_stats: list[ThreadStats]) -> dict:
    latency_count = sum(stat.latency_count for stat in thread_stats)
    latency_total_ms = sum(stat.latency_total_ms for stat in thread_stats)
    latency_max_ms = max((stat.latency_max_ms for stat in thread_stats), default=0.0)
    latency_buckets = [0] * len(LATENCY_BUCKETS_MS)
    for stat in thread_stats:
        for index, value in enumerate(stat.latency_buckets):
            latency_buckets[index] += value
    return {
        "completed": sum(stat.completed for stat in thread_stats),
        "failures": sum(stat.failures for stat in thread_stats),
        "set_ops": sum(stat.set_ops for stat in thread_stats),
        "get_ops": sum(stat.get_ops for stat in thread_stats),
        "bytes_written": sum(stat.bytes_written for stat in thread_stats),
        "bytes_read": sum(stat.bytes_read for stat in thread_stats),
        "latency_count": latency_count,
        "latency_total_ms": latency_total_ms,
        "latency_max_ms": latency_max_ms,
        "latency_buckets": latency_buckets,
    }


def progress_reporter(suite: dict, thread_stats: list[ThreadStats], started: float, stop_event: threading.Event):
    total_expected = STRESS_CLIENTS * STRESS_REQUESTS_PER_CLIENT
    while not stop_event.wait(REPORT_INTERVAL_SECONDS):
        totals = aggregate(thread_stats)
        elapsed = max(time.perf_counter() - started, 0.001)
        throughput = totals["completed"] / elapsed
        print(
            f"[PROGRESS] scenario={suite['name']} completed={totals['completed']}/{total_expected} "
            f"failures={totals['failures']} throughput_rps={throughput:.2f}"
        )


def run_stress(suite: dict) -> tuple[bool, list[str]]:
    threads = []
    thread_stats = []
    barrier = threading.Barrier(STRESS_CLIENTS)

    print(
        f"[INFO] stress scenario={suite['name']} profile=shared-auth-key-routing "
        f"clients={STRESS_CLIENTS} requests_per_client={STRESS_REQUESTS_PER_CLIENT} "
        f"ratio=set:{SET_PERCENT}% get:{GET_PERCENT}% hot_key={HOT_KEY_PERCENT}%/{HOT_KEY_COUNT}"
    )

    started = time.perf_counter()
    stop_event = threading.Event()
    reporter = None
    if REPORT_INTERVAL_SECONDS > 0:
        reporter = threading.Thread(
            target=progress_reporter,
            args=(suite, thread_stats, started, stop_event),
            daemon=True,
        )
        reporter.start()
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
    stop_event.set()
    if reporter is not None:
        reporter.join(timeout=1)
    elapsed = time.perf_counter() - started

    totals = aggregate(thread_stats)
    throughput = totals["completed"] / elapsed if elapsed > 0 else 0.0
    avg_latency = totals["latency_total_ms"] / totals["latency_count"] if totals["latency_count"] else 0.0
    p95 = percentile_from_buckets(totals["latency_buckets"], 0.95)
    p99 = percentile_from_buckets(totals["latency_buckets"], 0.99)

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
        f"latency_max_ms={totals['latency_max_ms']:.2f}",
        f"bytes_written={totals['bytes_written']}",
        f"bytes_read={totals['bytes_read']}",
    ]

    for line in summary:
        print(f"[SUMMARY] scenario={suite['name']} {line}")

    return totals["failures"] == 0, summary


def run_suite(suite: dict) -> bool:
    print("=== Camellia K8s stress-runner ===")
    print(
        f"scenario={suite['name']} profile=shared-auth-key-routing "
        f"sharedAuth={suite['shared_auth_host']}:{suite['shared_auth_port']} "
        f"keyRouting={suite['key_routing_host']}:{suite['key_routing_port']}"
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
    scenario_names = ",".join(suite["name"] for suite in scenarios)
    print(
        f"[RUN] scenarios={scenario_names} profile=shared-auth-key-routing clients={STRESS_CLIENTS} "
        f"req_per_client={STRESS_REQUESTS_PER_CLIENT} interval={RUN_INTERVAL_SECONDS}s"
    )
    overall = True
    results = {}
    for index, suite in enumerate(scenarios):
        ok = run_suite(suite)
        results[suite["name"]] = "PASS" if ok else "FAIL"
        if not ok:
            overall = False
        if index < len(scenarios) - 1 and SCENARIO_DELAY_SECONDS > 0:
            print(f"[INFO] sleeping {SCENARIO_DELAY_SECONDS}s before next scenario")
            time.sleep(SCENARIO_DELAY_SECONDS)
    print("[RUN] summary " + " ".join(f"{name}={status}" for name, status in results.items()))
    return 0 if overall else 1


def main():
    if not RUN_FOREVER:
        sys.exit(run_once())

    while True:
        code = run_once()
        if code != 0:
            print(f"[WARN] One or more checks failed. Next retry in {RUN_INTERVAL_SECONDS}s.")
        else:
            print(f"[INFO] All scenarios passed. Next retry in {RUN_INTERVAL_SECONDS}s.")
        time.sleep(RUN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
