import os
import sys
import time
import redis
from redis.exceptions import ResponseError


TEST_SCENARIO = os.environ.get("TEST_SCENARIO", "cluster").lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "camellia_admin_pass")
RUN_INTERVAL_SECONDS = int(os.environ.get("RUN_INTERVAL_SECONDS", "60"))
RUN_FOREVER = os.environ.get("RUN_FOREVER", "true").lower() == "true"

REDIS_CLIENT_KWARGS = {
    "decode_responses": True,
    "lib_name": None,
    "lib_version": None,
}


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

    def mset(self, pairs: dict):
        return self._retry_on_moved(lambda client: client.mset(pairs))

    def mget(self, keys: list[str]):
        return self._retry_on_moved(lambda client: client.mget(keys))


def get_conn(host: str, port: int, password: str | None):
    return ProxyClient(host, port, password)


def test_key_routing_basic(host: str, port: int, client_mode: str) -> tuple[bool, str]:
    key = f"k8s:runner:key-routing:{int(time.time())}"
    try:
        client = get_conn(host, port, ADMIN_PASSWORD)
        client.set(key, "ok")
        value = client.get(key)
        client.delete(key)
        if value == "ok":
            return True, "P1 pass"
        return False, f"P1 mismatch value={value}"
    except Exception as exc:
        return False, f"P1 error: {exc}"


def test_shared_auth_isolation(host: str, port: int, client_mode: str) -> tuple[bool, str]:
    key = f"k8s:runner:tenant:{int(time.time())}"
    try:
        order_client = get_conn(host, port, "svcOrderPwd")
        payment_client = get_conn(host, port, "svcPaymentPwd")
        order_client.set(key, "from_order")
        order_value = order_client.get(key)
        payment_value = payment_client.get(key)
        order_client.delete(key)
        if order_value == "from_order" and payment_value is None:
            return True, "P2 pass"
        return False, f"P2 mismatch order={order_value} payment={payment_value}"
    except Exception as exc:
        return False, f"P2 error: {exc}"


def test_cross_shard_pipeline(host: str, port: int, client_mode: str) -> tuple[bool, str]:
    if client_mode == "cluster":
        keys = [f"k8s:runner:cluster:{{tenant}}:{index}" for index in range(1, 6)]
    else:
        keys = [f"k8s:runner:cross-shard:{index}" for index in range(1, 6)]
    values = [f"v{index}" for index in range(1, 6)]
    try:
        client = get_conn(host, port, ADMIN_PASSWORD)
        for key, value in zip(keys, values):
            client.set(key, value)
        actual = client.mget(keys)

        for key in keys:
            client.delete(key)

        if actual == values:
            return True, "P3 pass"
        return False, f"P3 mismatch actual={actual} expected={values}"
    except Exception as exc:
        return False, f"P3 error: {exc}"


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


def run_suite(suite: dict) -> bool:
    print("=== Camellia K8s test-runner ===")
    print(
        f"scenario={suite['name']} mode={suite['client_mode']} "
        f"keyRouting={suite['key_routing_host']}:{suite['key_routing_port']} "
        f"sharedAuth={suite['shared_auth_host']}:{suite['shared_auth_port']}"
    )
    checks = [
        test_key_routing_basic(suite["key_routing_host"], suite["key_routing_port"], suite["client_mode"]),
        test_shared_auth_isolation(suite["shared_auth_host"], suite["shared_auth_port"], suite["client_mode"]),
        test_cross_shard_pipeline(suite["key_routing_host"], suite["key_routing_port"], suite["client_mode"]),
    ]
    success = True
    for passed, message in checks:
        if passed:
            print(f"[PASS] {message}")
        else:
            print(f"[FAIL] {message}")
            success = False
    return success


def run_once() -> int:
    scenarios = get_scenarios()
    overall = True
    for suite in scenarios:
        if not run_suite(suite):
            overall = False
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
