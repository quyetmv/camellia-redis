import os
import sys
import redis

PROXY_HOST = os.environ.get("PROXY_HOST", "localhost")
KEY_ROUTING_PORT = int(os.environ.get("KEY_ROUTING_PORT", 31681))
SHARED_AUTH_PORT = int(os.environ.get("SHARED_AUTH_PORT", 31680))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "camellia_admin_pass")

REDIS_CLIENT_KWARGS = {
    "decode_responses": True,
    "lib_name": None,
    "lib_version": None,
}


class Colors:
    OKGREEN = "\033[92m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_test(test_id, name):
    print(f"{Colors.BOLD}[TEST {test_id}]{Colors.ENDC} {name}...")


def print_pass(msg):
    print(f"  {Colors.OKGREEN}✓ PASS: {msg}{Colors.ENDC}")


def print_fail(msg):
    print(f"  {Colors.FAIL}✗ FAIL: {msg}{Colors.ENDC}")


def conn(port, password=None):
    return redis.Redis(host=PROXY_HOST, port=port, password=password, **REDIS_CLIENT_KWARGS)


def test_basic_set_get():
    print_test("S1", "Standalone key-routing SET/GET")
    key = "standalone:test:key1"
    try:
        client = conn(KEY_ROUTING_PORT, ADMIN_PASSWORD)
        client.set(key, "ok")
        value = client.get(key)
        client.delete(key)
        if value == "ok":
            print_pass("SET/GET qua key-routing thành công")
            return True
        print_fail(f"Unexpected value: {value}")
        return False
    except Exception as exc:
        print_fail(f"Connection failed: {exc}")
        return False


def test_shared_auth_isolation():
    print_test("S2", "Standalone shared-auth tenant isolation")
    tenants = {
        "svcOrderPwd": "order",
        "svcPaymentPwd": "payment",
    }
    key = "standalone:isolation:key"
    try:
        order_client = conn(SHARED_AUTH_PORT, "svcOrderPwd")
        payment_client = conn(SHARED_AUTH_PORT, "svcPaymentPwd")

        order_client.set(key, "from_order")
        order_val = order_client.get(key)
        payment_val = payment_client.get(key)

        order_client.delete(key)

        if order_val == "from_order" and payment_val is None:
            print_pass("2 tenant tách biệt dữ liệu đúng kỳ vọng")
            return True

        print_fail(f"Isolation mismatch: order={order_val}, payment={payment_val}")
        return False
    except Exception as exc:
        print_fail(f"Tenant test failed: {exc}")
        return False


def test_multi_key_read():
    print_test("S3", "Standalone multi-key read (pipeline)")
    payload = {f"standalone:bulk:{index}": f"v{index}" for index in range(1, 6)}
    try:
        client = conn(KEY_ROUTING_PORT, ADMIN_PASSWORD)
        client.mset(payload)

        pipe = client.pipeline(transaction=False)
        for key in payload:
            pipe.get(key)
        values = pipe.execute()

        for key in payload:
            client.delete(key)

        expected = list(payload.values())
        if values == expected:
            print_pass("Pipeline multi-key GET trả về đúng dữ liệu")
            return True

        print_fail(f"Pipeline mismatch: {values} != {expected}")
        return False
    except Exception as exc:
        print_fail(f"Pipeline test failed: {exc}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 56)
    print("  CAMELLIA PROXY STANDALONE TESTS")
    print("=" * 56)

    results = {
        "S1": test_basic_set_get(),
        "S2": test_shared_auth_isolation(),
        "S3": test_multi_key_read(),
    }

    passed = sum(1 for status in results.values() if status)
    print(f"\nSummary: {passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)
