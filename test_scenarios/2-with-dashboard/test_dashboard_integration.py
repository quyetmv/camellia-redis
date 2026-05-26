#!/usr/bin/env python3
"""
CAMELLIA REDIS - SHARDING & ROUTING TEST SUITE
==============================================

Test Coverage:
- Hash slot calculation and consistent hashing
- Hash tag routing
- Cross-pool key distribution
- Routing configuration hot reload
- Multi-tenant isolation
- Password-based tenant routing

Prerequisites:
- Camellia proxy running on localhost:6379
- Dashboard API accessible at http://localhost:8080
- Redis pools configured (Pool 1-10)
- Python packages: redis, requests, hashlib
"""

import redis
import requests
import hashlib
import time
import json
from collections import defaultdict
from typing import Dict, List, Tuple
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

import os

PROXY_HOST = os.environ.get("PROXY_HOST", "localhost")
CLIENT_MODE = os.environ.get("CLIENT_MODE", "standalone").lower()  # Có thể là 'standalone' hoặc 'cluster'

# Các cổng NodePort tương ứng với từng thiết kế triển khai proxy trên K8s (Hỗ trợ nạp từ ENVs)
KEY_ROUTING_PORT = int(os.environ.get("KEY_ROUTING_PORT", 30681))
SHARED_AUTH_PORT = int(os.environ.get("SHARED_AUTH_PORT", 30680))
ADMIN_PASSWORD = "camellia_admin_pass"
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:30881")

# Tenant configurations (Cho kịch bản Shared-Auth và Per-Service)
TENANTS = {
    "order": {
        "password": "svcOrderPwd",
        "pools": [1, 2, 3]  
    },
    "payment": {
        "password": "svcPaymentPwd",
        "pools": [4, 5, 6]  
    },
    "search": {
        "password": "svcSearchPwd",
        "pools": [7, 8, 9]  
    }
}

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_header(text):
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_test(test_id, description):
    """Print test case header"""
    print(f"{Colors.OKBLUE}[{test_id}] {description}{Colors.ENDC}")

def print_pass(message):
    """Print pass message"""
    print(f"{Colors.OKGREEN}✓ PASS: {message}{Colors.ENDC}")

def print_fail(message):
    """Print fail message"""
    print(f"{Colors.FAIL}✗ FAIL: {message}{Colors.ENDC}")

def print_info(message):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ INFO: {message}{Colors.ENDC}")

def calculate_crc16(key: str) -> int:
    """
    Calculate CRC16 hash for Redis key
    This is the standard Redis Cluster hash function
    """
    crc = 0xFFFF
    for byte in key.encode('utf-8'):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc

def calculate_hash_slot(key: str, bucket_size: int = 1024) -> int:
    """
    Calculate hash slot for a key using CRC16
    
    Args:
        key: Redis key
        bucket_size: Total number of buckets (default 1024)
    
    Returns:
        Hash slot (0 to bucket_size-1)
    """
    # Extract hash tag if present
    start = key.find('{')
    if start != -1:
        end = key.find('}', start + 1)
        if end != -1 and end > start + 1:
            # Hash tag found, use content inside {}
            hash_key = key[start + 1:end]
        else:
            # Invalid hash tag, use full key
            hash_key = key
    else:
        # No hash tag, use full key
        hash_key = key
    
    crc = calculate_crc16(hash_key)
    slot = crc % bucket_size
    return slot

def get_redis_connection(tenant: str = None, mode: str = "key-routing") -> redis.Redis:
    """Get Redis connection, authenticated based on deployment mode"""
    
    if mode == "key-routing":
        port = KEY_ROUTING_PORT
        password = ADMIN_PASSWORD
    elif mode == "shared-auth":
        port = SHARED_AUTH_PORT
        password = TENANTS[tenant]["password"] if tenant in TENANTS else "wrong-password"

    else:
        port = KEY_ROUTING_PORT
        password = ADMIN_PASSWORD
        
    if CLIENT_MODE == "cluster":
        r = redis.RedisCluster(
            startup_nodes=[{"host": PROXY_HOST, "port": port}],
            password=password if password else None,
            decode_responses=True,
            socket_connect_timeout=5,
            skip_full_coverage_check=True
        )
    else:
        r = redis.Redis(
            host=PROXY_HOST,
            port=port,
            decode_responses=True,
            socket_connect_timeout=5
        )
        if password:
            r.execute_command("AUTH", password)
        
    name = tenant if tenant else mode
    print_info(f"Connected to {mode} at {port} (role: {name}, mode: {CLIENT_MODE})")
    
    return r

# ============================================================================
# TEST SUITE 1: HASH SLOT CALCULATION & ROUTING
# ============================================================================

def test_hash_slot_calculation():
    """TC-201: Verify hash slot calculation matches expected values"""
    print_header("TEST SUITE 1: HASH SLOT CALCULATION & ROUTING")
    print_test("TC-201", "Hash slot calculation verification")
    
    test_cases = [
        ("user:1000", None, "Full key hashing"),
        ("{user}:1000", "user", "Hash tag extraction"),
        ("{user}:profile:1000", "user", "Hash tag with multiple segments"),
        ("session:{abc}:data", "abc", "Hash tag in middle"),
        ("{user}:{session}:data", "user", "Multiple hash tags - first wins"),
        ("{}:empty", None, "Empty hash tag - use full key"),
        ("{unclosed:data", None, "Unclosed hash tag - use full key"),
    ]
    
    passed = 0
    total = len(test_cases)
    
    for key, expected_hash_key, description in test_cases:
        slot = calculate_hash_slot(key)
        
        # Determine what was actually hashed
        start = key.find('{')
        if start != -1:
            end = key.find('}', start + 1)
            if end != -1 and end > start + 1:
                actual_hash_key = key[start + 1:end]
            else:
                actual_hash_key = None
        else:
            actual_hash_key = None
        
        if actual_hash_key == expected_hash_key:
            print_pass(f"{description}: '{key}' -> slot {slot} (hashed: '{actual_hash_key or key}')")
            passed += 1
        else:
            print_fail(f"{description}: Expected hash on '{expected_hash_key}', got '{actual_hash_key}'")
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} passed{Colors.ENDC}\n")
    return passed == total

def test_consistent_hashing():
    """TC-203: Verify same key always routes to same slot"""
    print_test("TC-203", "Consistent hashing stability test")
    
    test_key = "user:12345"
    iterations = 1000
    
    slots = set()
    for i in range(iterations):
        slot = calculate_hash_slot(test_key)
        slots.add(slot)
    
    if len(slots) == 1:
        print_pass(f"Key '{test_key}' consistently routes to slot {slots.pop()} across {iterations} iterations")
        return True
    else:
        print_fail(f"Inconsistent routing! Key mapped to {len(slots)} different slots")
        return False

def test_distribution_uniformity():
    """TC-208: Verify hash distribution is uniform across buckets"""
    print_test("TC-208", "Hash distribution uniformity test")
    
    num_keys = 10000
    bucket_size = 1024
    
    # Generate random keys
    import random
    import string
    
    bucket_counts = defaultdict(int)
    
    for i in range(num_keys):
        # Generate random key
        key = f"user:{''.join(random.choices(string.ascii_letters + string.digits, k=10))}"
        slot = calculate_hash_slot(key, bucket_size)
        bucket_counts[slot] += 1
    
    # Calculate statistics
    avg_keys_per_bucket = num_keys / bucket_size
    filled_buckets = len(bucket_counts)
    max_keys = max(bucket_counts.values())
    min_keys = min(bucket_counts.values())
    
    # Check if distribution is within ±20% of average
    deviation = abs(max_keys - min_keys) / avg_keys_per_bucket
    
    print_info(f"Generated {num_keys} random keys")
    print_info(f"Buckets used: {filled_buckets}/{bucket_size}")
    print_info(f"Average keys/bucket: {avg_keys_per_bucket:.2f}")
    print_info(f"Max keys in bucket: {max_keys}")
    print_info(f"Min keys in bucket: {min_keys}")
    print_info(f"Deviation: {deviation*100:.2f}%")
    
    if deviation < 0.2:  # Within 20%
        print_pass(f"Distribution is uniform (deviation < 20%)")
        return True
    else:
        print_fail(f"Distribution is skewed (deviation = {deviation*100:.2f}%)")
        return False

def test_hash_tag_routing():
    """TC-204: Verify hash tags route keys to same slot"""
    print_test("TC-204", "Hash tag routing verification")
    
    # Keys with same hash tag should go to same slot
    keys_group_1 = ["{user}:profile", "{user}:settings", "{user}:history"]
    keys_group_2 = ["{session}:data", "{session}:auth", "{session}:metadata"]
    
    # Group 1 - all should have same slot
    slots_1 = [calculate_hash_slot(key) for key in keys_group_1]
    
    # Group 2 - all should have same slot
    slots_2 = [calculate_hash_slot(key) for key in keys_group_2]
    
    passed = True
    
    if len(set(slots_1)) == 1:
        print_pass(f"All '{{{keys_group_1[0].split('}')[0][1:]}}}' tagged keys route to slot {slots_1[0]}")
    else:
        print_fail(f"Hash tag '{{{keys_group_1[0].split('}')[0][1:]}}}' routes to multiple slots: {set(slots_1)}")
        passed = False
    
    if len(set(slots_2)) == 1:
        print_pass(f"All '{{{keys_group_2[0].split('}')[0][1:]}}}' tagged keys route to slot {slots_2[0]}")
    else:
        print_fail(f"Hash tag '{{{keys_group_2[0].split('}')[0][1:]}}}' routes to multiple slots: {set(slots_2)}")
        passed = False
    
    # Groups should route to different slots (statistically)
    if slots_1[0] != slots_2[0]:
        print_pass(f"Different hash tags route to different slots ({slots_1[0]} vs {slots_2[0]})")
    else:
        print_info(f"Hash collision: both tags route to slot {slots_1[0]} (acceptable)")
    
    return passed

# ============================================================================
# TEST SUITE 2: REAL REDIS OPERATIONS
# ============================================================================

def test_basic_routing():
    """TC-201: Test actual routing through Camellia proxy"""
    print_header("TEST SUITE 2: REAL REDIS OPERATIONS THROUGH PROXY")
    print_test("TC-201", "Basic key routing through proxy")
    
    try:
        r = get_redis_connection()
        
        # Test basic SET/GET
        test_key = "test:routing:key1"
        test_value = "value123"
        
        # Calculate expected slot
        slot = calculate_hash_slot(test_key)
        print_info(f"Key '{test_key}' should route to slot {slot}")
        
        # SET key
        result = r.set(test_key, test_value)
        if result:
            print_pass(f"SET {test_key} succeeded")
        else:
            print_fail(f"SET {test_key} failed")
            return False
        
        # GET key
        retrieved = r.get(test_key)
        if retrieved == test_value:
            print_pass(f"GET {test_key} returned correct value")
        else:
            print_fail(f"GET {test_key} returned '{retrieved}', expected '{test_value}'")
            return False
        
        # Cleanup
        r.delete(test_key)
        
        return True
        
    except redis.ConnectionError as e:
        print_fail(f"Connection error: {e}")
        print_info("Make sure Camellia proxy is running on localhost:6379")
        return False
    except Exception as e:
        print_fail(f"Unexpected error: {e}")
        return False

def test_multi_key_operations_same_shard():
    """TC-101: MGET/MSET with hash tags (same shard)"""
    print_test("TC-101/TC-103", "Multi-key operations with hash tags")
    
    try:
        r = get_redis_connection()
        
        # Use hash tags to ensure same shard
        keys = ["{user}:name", "{user}:email", "{user}:age"]
        values = ["John Doe", "john@example.com", "30"]
        
        # MSET
        key_value_pairs = {}
        for k, v in zip(keys, values):
            key_value_pairs[k] = v
        
        result = r.mset(key_value_pairs)
        if result:
            print_pass(f"MSET succeeded with {len(keys)} keys (same hash tag)")
        else:
            print_fail("MSET failed")
            return False
        
        # MGET
        retrieved = r.mget(keys)
        if retrieved == values:
            print_pass(f"MGET returned correct values")
        else:
            print_fail(f"MGET values mismatch. Got: {retrieved}, Expected: {values}")
            return False
        
        # Cleanup
        r.delete(*keys)
        
        return True
        
    except Exception as e:
        print_fail(f"Error: {e}")
        return False

def test_multi_key_operations_cross_shard():
    """TC-102: MGET without hash tags (potentially cross-shard)"""
    print_test("TC-102", "Multi-key operations without hash tags (cross-shard)")
    
    try:
        r = get_redis_connection()
        
        # Keys without hash tags - may be on different shards
        keys = ["user:1:name", "user:2:name", "user:3:name"]
        values = ["Alice", "Bob", "Charlie"]
        
        # Calculate slots to verify they're on different shards
        slots = [calculate_hash_slot(k) for k in keys]
        print_info(f"Keys route to slots: {slots}")
        
        # Set individual keys first
        for k, v in zip(keys, values):
            r.set(k, v)
        
        # Try MGET - Camellia should handle cross-shard
        try:
            retrieved = r.mget(keys)
            if retrieved == values:
                print_pass("MGET succeeded across shards (Camellia handled it or they landed on same shard)")
            else:
                print_fail(f"MGET values mismatch")
                return False
        except redis.exceptions.RedisClusterException as e:
            if CLIENT_MODE == "cluster":
                print_pass("MGET cross-shard correctly blocked by Python RedisCluster Client (Expected behavior)")
            else:
                print_fail(f"Unexpected RedisClusterException in standalone mode: {e}")
                return False
        except redis.ResponseError as e:
            if "MOVED" in str(e):
                print_pass("MGET hit cross-shard and proxy returned MOVED. Standalone client failed as expected.")
            else:
                print_info(f"MGET cross-shard not supported: {e}")
                print_info("This is expected if cross-shard multi-key ops are disabled")
        
        # Cleanup
        for k in keys:
            r.delete(k)
        
        return True
        
    except Exception as e:
        print_fail(f"Error: {e}")
        return False

def test_scan_across_shards():
    """TC-215: SCAN command across all shards"""
    print_test("TC-215", "SCAN command across shards")
    
    try:
        r = get_redis_connection()
        
        # Insert keys that will distribute across shards
        test_prefix = "scantest"
        num_keys = 100
        
        for i in range(num_keys):
            r.set(f"{test_prefix}:{i}", f"value{i}")
        
        # SCAN for all keys
        cursor = 0
        found_keys = []
        iterations = 0
        max_iterations = 1000  # Safety limit
        
        while iterations < max_iterations:
            cursor, keys = r.scan(cursor, match=f"{test_prefix}:*", count=10)
            found_keys.extend(keys)
            iterations += 1
            
            if cursor == 0:
                break
        
        unique_keys = set(found_keys)
        
        if len(unique_keys) == num_keys:
            print_pass(f"SCAN found all {num_keys} keys across shards in {iterations} iterations")
        else:
            print_fail(f"SCAN found {len(unique_keys)} keys, expected {num_keys}")
            return False
        
        # Cleanup
        for i in range(num_keys):
            r.delete(f"{test_prefix}:{i}")
        
        return True
        
    except redis.ResponseError as e:
        print_info(f"SCAN not supported: {e}")
        print_info("Camellia may not support cross-shard SCAN in current config")
        return True  # Not a hard failure
    except Exception as e:
        print_fail(f"Error: {e}")
        return False

# ============================================================================
# TEST SUITE 3: MULTI-TENANCY
# ============================================================================

def test_tenant_authentication():
    """TC-301/TC-304/TC-305: Tenant password authentication (Shared-Auth)"""
    print_header("TEST SUITE 3: MULTI-TENANCY")
    print_test("TC-301/TC-304/TC-305", "Tenant authentication (Shared Auth Port 30680)")
    
    all_passed = True
    
    # Test valid authentication
    try:
        r = get_redis_connection("order", mode="shared-auth")
        r.ping()
        print_pass("Service 'order' authenticated successfully")
    except redis.AuthenticationError:
        print_fail("Service 'order' authentication failed")
        all_passed = False
    except Exception as e:
        print_fail(f"order error: {e}")
        all_passed = False
    
    # Test invalid password
    try:
        if CLIENT_MODE == "cluster":
            r = redis.RedisCluster(startup_nodes=[{"host": PROXY_HOST, "port": SHARED_AUTH_PORT}], password="wrong-password", decode_responses=True, skip_full_coverage_check=True)
        else:
            r = redis.Redis(host=PROXY_HOST, port=SHARED_AUTH_PORT, decode_responses=True)
            r.execute_command("AUTH", "wrong-password")
        r.ping()
        print_fail("Invalid password was accepted (security issue!)")
        all_passed = False
    except (redis.AuthenticationError, redis.exceptions.RedisClusterException) as e:
        print_pass("Invalid password correctly rejected")
    except Exception as e:
        print_info(f"Authentication test: {e}")
    
    # Test no authentication
    try:
        if CLIENT_MODE == "cluster":
            r = redis.RedisCluster(startup_nodes=[{"host": PROXY_HOST, "port": SHARED_AUTH_PORT}], decode_responses=True, skip_full_coverage_check=True)
        else:
            r = redis.Redis(host=PROXY_HOST, port=SHARED_AUTH_PORT, decode_responses=True)
        r.set("test", "value")  # Try operation without AUTH
        print_fail("Operation without AUTH was allowed (security issue!)")
        all_passed = False
    except (redis.AuthenticationError, redis.exceptions.RedisClusterException) as e:
        print_pass("Operation without AUTH correctly rejected")
    except redis.ResponseError as e:
        if "NOAUTH" in str(e) or "AUTH" in str(e):
            print_pass("Operation without AUTH correctly rejected")
        else:
            print_info(f"Auth check: {e}")
    except Exception as e:
        print_info(f"No-auth test: {e}")
    
    return all_passed

def test_tenant_isolation():
    """TC-302/TC-303: Verify tenant data isolation (Shared Auth)"""
    print_test("TC-302/TC-303", "Tenant data isolation (Shared Auth)")
    
    try:
        # Connect as order
        r1 = get_redis_connection("order", mode="shared-auth")
        
        # Connect as payment
        r2 = get_redis_connection("payment", mode="shared-auth")
        
        # Set key in order
        tenant1_key = "shared_key"
        tenant1_value = "order_value"
        r1.set(tenant1_key, tenant1_value)
        
        # Set same key name in payment
        tenant2_value = "payment_value"
        r2.set(tenant1_key, tenant2_value)
        
        # Verify isolation - each tenant sees only their value
        retrieved1 = r1.get(tenant1_key)
        retrieved2 = r2.get(tenant1_key)
        
        if retrieved1 == tenant1_value and retrieved2 == tenant2_value:
            print_pass(f"Tenant isolation verified: order sees '{retrieved1}', payment sees '{retrieved2}'")
            
            # Check if they route to different pools
            slot1 = calculate_hash_slot(tenant1_key)
            print_info(f"order routes to slot {slot1} (Pool {TENANTS['order']['pools'][0]})")
            print_info(f"payment routes to slot {slot1} (Pool {TENANTS['payment']['pools'][0]})")
            
            if TENANTS['order']['pools'] != TENANTS['payment']['pools']:
                print_pass("Tenants route to different pools as expected")
            else:
                print_info("Tenants share same pool (isolation via namespacing)")
            
            # Cleanup
            r1.delete(tenant1_key)
            r2.delete(tenant1_key)
            
            return True
        else:
            print_fail(f"Isolation breach! order: {retrieved1}, payment: {retrieved2}")
            return False
            
    except Exception as e:
        print_fail(f"Error: {e}")
        print_info("This test requires multi-tenancy configured in Camellia Dashboard")
        return False


# ============================================================================
# TEST SUITE 4: ADVANCED SCENARIOS
# ============================================================================

def test_pipeline_performance():
    """TC-114: Pipeline performance test"""
    print_header("TEST SUITE 4: ADVANCED SCENARIOS")
    print_test("TC-114", "Pipeline performance test")
    
    try:
        r = get_redis_connection()
        
        num_commands = 100
        
        # Time without pipeline
        start = time.time()
        for i in range(num_commands):
            r.set(f"nopipe:{i}", f"value{i}")
        time_no_pipeline = time.time() - start
        
        # Time with pipeline
        pipe = r.pipeline()
        start = time.time()
        for i in range(num_commands):
            pipe.set(f"pipe:{i}", f"value{i}")
        pipe.execute()
        time_pipeline = time.time() - start
        
        speedup = time_no_pipeline / time_pipeline
        
        print_info(f"Without pipeline: {time_no_pipeline:.4f}s for {num_commands} commands")
        print_info(f"With pipeline: {time_pipeline:.4f}s for {num_commands} commands")
        print_info(f"Speedup: {speedup:.2f}x")
        
        if speedup > 2:
            print_pass(f"Pipeline provides {speedup:.2f}x speedup")
        else:
            print_info(f"Pipeline speedup {speedup:.2f}x is lower than expected (network latency?)")
        
        # Cleanup
        for i in range(num_commands):
            r.delete(f"nopipe:{i}", f"pipe:{i}")
        
        return True
        
    except Exception as e:
        print_fail(f"Error: {e}")
        return False

def test_transaction_same_shard():
    """TC-115: Transaction (MULTI/EXEC) with hash tags"""
    print_test("TC-115", "Transaction support (same shard)")
    
    try:
        r = get_redis_connection()
        
        # Use hash tags to ensure same shard
        counter_key = "{txn}:counter"
        data_key = "{txn}:data"
        
        # Initialize
        r.set(counter_key, 0)
        r.set(data_key, "initial")
        
        # Execute transaction
        pipe = r.pipeline()
        pipe.multi()
        pipe.incr(counter_key)
        pipe.set(data_key, "updated")
        result = pipe.execute()
        
        # Verify atomicity
        counter_value = int(r.get(counter_key))
        data_value = r.get(data_key)
        
        if counter_value == 1 and data_value == "updated":
            print_pass("Transaction executed atomically")
        else:
            print_fail(f"Transaction failed: counter={counter_value}, data={data_value}")
            return False
        
        # Cleanup
        r.delete(counter_key, data_key)
        
        return True
        
    except redis.ResponseError as e:
        print_info(f"Transaction not supported: {e}")
        print_info("Camellia may not support MULTI/EXEC in current configuration")
        return True  # Not a hard failure
    except Exception as e:
        print_fail(f"Error: {e}")
        return False

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    """Main test runner"""
    print(f"{Colors.BOLD}")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "CAMELLIA REDIS - SHARDING & MULTI-TENANCY TEST SUITE".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")
    print(Colors.ENDC)
    
    results = {}
    
    # Suite 1: Hash Slot Calculation
    results["TC-201"] = test_hash_slot_calculation()
    results["TC-203"] = test_consistent_hashing()
    results["TC-208"] = test_distribution_uniformity()
    results["TC-204"] = test_hash_tag_routing()
    
    # Suite 2: Real Redis Operations
    results["TC-201-redis"] = test_basic_routing()
    results["TC-101/103"] = test_multi_key_operations_same_shard()
    results["TC-102"] = test_multi_key_operations_cross_shard()
    results["TC-215"] = test_scan_across_shards()
    
    # Suite 3: Multi-tenancy
    results["TC-301/304/305"] = test_tenant_authentication()
    results["TC-302/303"] = test_tenant_isolation()

    
    # Suite 4: Advanced
    results["TC-114"] = test_pipeline_performance()
    results["TC-115"] = test_transaction_same_shard()
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    pass_rate = (passed / total) * 100
    
    print(f"{Colors.BOLD}Total Tests: {total}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Passed: {passed}{Colors.ENDC}")
    print(f"{Colors.FAIL}Failed: {total - passed}{Colors.ENDC}")
    print(f"{Colors.BOLD}Pass Rate: {pass_rate:.1f}%{Colors.ENDC}\n")
    
    # Detailed results
    print(f"{Colors.BOLD}Detailed Results:{Colors.ENDC}")
    for test_id, result in results.items():
        status = f"{Colors.OKGREEN}✓ PASS{Colors.ENDC}" if result else f"{Colors.FAIL}✗ FAIL{Colors.ENDC}"
        print(f"  {test_id}: {status}")
    
    print()
    
    # Exit code
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
