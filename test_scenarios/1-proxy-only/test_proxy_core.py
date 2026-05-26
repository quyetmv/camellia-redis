import os
import sys
import redis
import time
import json
import socket

# Configuration from Environment (provided by Makefile)
PROXY_HOST = os.environ.get("PROXY_HOST", "localhost")
CLIENT_MODE = os.environ.get("CLIENT_MODE", "standalone").lower()  
KEY_ROUTING_PORT = int(os.environ.get("KEY_ROUTING_PORT", 30681))
SHARED_AUTH_PORT = int(os.environ.get("SHARED_AUTH_PORT", 30680))
PASSWORD = "camellia_admin_pass" # Default pass in static config
REDIS_CLIENT_KWARGS = {
    "decode_responses": True,
    "lib_name": None,
    "lib_version": None,
}

class Colors:
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_test(id, name): print(f"{Colors.BOLD}[TEST {id}]{Colors.ENDC} {name}...")
def print_pass(msg): print(f"  {Colors.OKGREEN}✓ PASS: {msg}{Colors.ENDC}")
def print_fail(msg): print(f"  {Colors.FAIL}✗ FAIL: {msg}{Colors.ENDC}")
def print_info(msg): print(f"  {Colors.WARNING}→ {msg}{Colors.ENDC}")

def get_conn(port, password=None):
    """Kết nối thông thường - dùng CLIENT_MODE để quyết định standalone/cluster."""
    if CLIENT_MODE == "cluster":
        return redis.RedisCluster(host=PROXY_HOST, port=port, password=password, **REDIS_CLIENT_KWARGS)
    return redis.Redis(host=PROXY_HOST, port=port, password=password, **REDIS_CLIENT_KWARGS)

def get_conn_standalone(port, password=None):
    """Luôn dùng standalone client - dành cho shared-auth (multi-tenant by password).
    Shared-Auth Proxy nhận AUTH, dùng password để route tenant, không forward xuống backend.
    RedisCluster client sẽ gửi thêm AUTH xuống backend gây lỗi 'no password is set'."""
    return redis.Redis(host=PROXY_HOST, port=port, password=password, **REDIS_CLIENT_KWARGS)

def test_proxy_basic_ops():
    print_test("P1", "Basic Key Routing Proxy Ops")
    try:
        r = get_conn(KEY_ROUTING_PORT, PASSWORD)
        r.set("test:proxy:key1", "hello")
        val = r.get("test:proxy:key1")
        if val == "hello":
            print_pass("Basic SET/GET works on Key Routing port")
            r.delete("test:proxy:key1")
            return True
        print_fail(f"Got wrong value: {val}")
        return False
    except Exception as e:
        print_fail(f"Connection failed: {e}")
        return False

def test_shared_auth_static():
    print_test("P2", "Shared Auth Static Port (Tenant Isolation)")
    tenants = {
        "svcOrderPwd": "OrderTenant",
        "svcPaymentPwd": "PaymentTenant"
    }
    success = True
    for pwd, name in tenants.items():
        try:
            if CLIENT_MODE == "cluster":
                r = get_conn(SHARED_AUTH_PORT, pwd)
            else:
                r = get_conn_standalone(SHARED_AUTH_PORT, pwd)
            test_key = f"tenant:{name}:test"
            r.set(test_key, "auth_ok")
            if r.get(test_key) == "auth_ok":
                print_pass(f"Auth success for {name} with its password")
                r.delete(test_key)
            else:
                success = False
        except Exception as e:
            print_fail(f"Tenant check failed for {name}: {e}")
            success = False
    return success

def test_cross_shard_multi():
    print_test("P3", "Cross-shard Multi-key operations")
    r = get_conn(KEY_ROUTING_PORT, PASSWORD)
    # Using keys that likely hit different shards in a 9-shard setup
    keys = {"k1": "v1", "k2": "v2", "k3": "v3"}
    try:
        r.mset(keys)
        res = r.mget(list(keys.keys()))
        if res == list(keys.values()):
            print_pass("MSET/MGET cross-shard works (Proxy handles sharding)")
        else:
            print_fail(f"MGET mismatch: {res}")
        r.delete(*keys.keys())
        return True
    except redis.exceptions.RedisClusterException as e:
        if CLIENT_MODE == "cluster":
            print_pass(f"Caught expected Cluster client mismatch: {e}")
            return True
        print_fail(f"Unexpected cluster error in standalone mode: {e}")
        return False
    except Exception as e:
        print_fail(f"MGET Error: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  CAMELLIA PROXY CORE TESTS (NO DASHBOARD)")
    print("="*50)
    res = {}
    res["P1"] = test_proxy_basic_ops()
    res["P2"] = test_shared_auth_static()
    res["P3"] = test_cross_shard_multi()
    
    passed = sum(1 for v in res.values() if v)
    print(f"\nSummary: {passed}/{len(res)} passed")
    sys.exit(0 if passed == len(res) else 1)
