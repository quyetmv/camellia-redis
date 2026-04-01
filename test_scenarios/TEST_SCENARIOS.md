# CAMELLIA REDIS - SHARDING & MULTI-TENANCY TEST SCENARIOS
# =========================================================

> Note: Một phần hướng dẫn bên dưới phản ánh môi trường Sentinel tổng quát. Với repo hiện tại, bộ test chạy thực tế là `1-proxy-only/test_proxy_core.py`, `1-proxy-only/test_proxy_standalone.py`, `2-with-dashboard/test_dashboard_integration.py`, và `../scripts/stress_test.py`.

## TABLE OF CONTENTS
1. Test Environment Setup
2. Automated Test Execution
3. Manual Test Scenarios
4. Performance Benchmarking
5. Troubleshooting Guide

---

## 1. TEST ENVIRONMENT SETUP

### Prerequisites

**Infrastructure:**
- Camellia Proxy: localhost:6379 (or configure in test script)
- Camellia Dashboard: http://localhost:8080
- Redis Pools: 10 pools (Pool 1-10) with Sentinel
- Python 3.8+

**Python Dependencies:**
```bash
pip install redis requests
```

**Configuration Files:**
- `1-proxy-only/test_proxy_core.py` - Proxy core test (No Dashboard)
- `2-with-dashboard/test_dashboard_integration.py` - Full integration test
- `2-with-dashboard/camellia_dashboard_config.txt` - Dashboard configuration

### Setup Steps

**Step 1: Configure Camellia Dashboard**
```bash
# Extract setup script from config file and execute
bash setup_dashboard.sh

# Or manually via Dashboard UI:
# 1. Login to http://localhost:8080
# 2. Navigate to Resource Table Management
# 3. Create 3 resource tables (service-group-1, 2, 3)
# 4. Configure password mappings
```

**Step 2: Configure Multi-tenant Passwords**

In Camellia Proxy configuration, ensure dynamic tenant routing is enabled:

```yaml
# application.yml
camellia-redis-proxy:
  transpond:
    type: remote
    remote:
      url: http://localhost:8080
      dynamic: true  # Enable multi-tenant
```

**Step 3: Verify Connectivity**
```bash
# Test proxy connection
redis-cli -h localhost -p 6379 PING
# Expected: PONG (or AUTH required)

# Test Dashboard API
curl http://localhost:8080/camellia/admin/health
# Expected: {"status":"UP"}
```

---

## 2. AUTOMATED TEST EXECUTION

### Running the Full Test Suite

```bash
# Run all tests
python test_camellia_sharding.py

# Expected output:
# ================================================================================
#            CAMELLIA REDIS - SHARDING & MULTI-TENANCY TEST SUITE
# ================================================================================
#
# [Suite 1] Hash Slot Calculation
# [Suite 2] Real Redis Operations  
# [Suite 3] Multi-tenancy
# [Suite 4] Advanced Scenarios
#
# TEST SUMMARY
# Total Tests: 13
# Passed: 13
# Failed: 0
# Pass Rate: 100.0%
```

### Individual Test Suites

To run specific test suites, modify the `main()` function:

```python
# Run only hash calculation tests
results = {}
results["TC-201"] = test_hash_slot_calculation()
results["TC-203"] = test_consistent_hashing()
```

### Test Output Interpretation

**Colors:**
- 🟢 Green ✓ PASS = Test passed successfully
- 🔴 Red ✗ FAIL = Test failed, requires investigation
- 🔵 Blue ℹ INFO = Informational message
- 🟡 Yellow (none) = Not used currently

**Common Test Results:**

```
✓ PASS: Key 'user:1000' -> slot 342 (hashed: 'user:1000')
  → Hash calculation working correctly

✗ FAIL: MGET values mismatch. Got: [...], Expected: [...]
  → Cross-shard MGET may not be supported, check Camellia config

ℹ INFO: SCAN not supported: ERR unknown command 'SCAN'
  → Feature not available in current Camellia version (acceptable)
```

---

## 3. MANUAL TEST SCENARIOS

### Scenario 1: Basic Sharding Verification

**Objective:** Verify keys route to correct pools based on hash

**Steps:**

1. **Calculate expected slot for test keys:**
   ```python
   from test_camellia_sharding import calculate_hash_slot
   
   print(calculate_hash_slot("user:1000"))  # e.g., slot 342
   print(calculate_hash_slot("user:2000"))  # e.g., slot 789
   ```

2. **Connect to proxy and insert keys:**
   ```bash
   redis-cli -h localhost -p 6379
   
   127.0.0.1:6379> SET user:1000 "Alice"
   OK
   127.0.0.1:6379> SET user:2000 "Bob"
   OK
   ```

3. **Verify keys exist:**
   ```bash
   127.0.0.1:6379> GET user:1000
   "Alice"
   127.0.0.1:6379> GET user:2000
   "Bob"
   ```

4. **Check which pool stores each key (via monitoring):**
   ```bash
   # Check Redis Pool 1
   redis-cli -h 10.1.10.10 -p 6379 -a pool1-redis-password KEYS "user:*"
   
   # Check Redis Pool 2
   redis-cli -h 10.1.20.10 -p 6379 -a pool2-redis-password KEYS "user:*"
   
   # Keys should be distributed across pools
   ```

**Expected Result:** Keys distribute across pools based on hash slots

---

### Scenario 2: Hash Tag Routing

**Objective:** Verify hash tags route related keys to same shard

**Steps:**

1. **Insert keys with same hash tag:**
   ```bash
   redis-cli -h localhost -p 6379
   
   127.0.0.1:6379> SET {user}:1:profile "Profile data"
   OK
   127.0.0.1:6379> SET {user}:1:settings "Settings data"
   OK
   127.0.0.1:6379> SET {user}:1:history "History data"
   OK
   ```

2. **Perform multi-key operation:**
   ```bash
   127.0.0.1:6379> MGET {user}:1:profile {user}:1:settings {user}:1:history
   1) "Profile data"
   2) "Settings data"
   3) "History data"
   ```

3. **Verify all keys on same pool:**
   ```bash
   # Check a single pool - all 3 keys should be there
   redis-cli -h 10.1.10.10 -p 6379 -a pool1-redis-password KEYS "{user}:1:*"
   ```

**Expected Result:** All keys with same hash tag {user} on same pool, MGET succeeds

---

### Scenario 3: Multi-tenant Isolation

**Objective:** Verify tenants see isolated data

**Steps:**

1. **Connect as Tenant 1:**
   ```bash
   redis-cli -h localhost -p 6379
   
   127.0.0.1:6379> AUTH tenant1-password
   OK
   127.0.0.1:6379> SET customer:100 "Tenant1 Customer"
   OK
   127.0.0.1:6379> GET customer:100
   "Tenant1 Customer"
   ```

2. **Connect as Tenant 2 (new connection):**
   ```bash
   redis-cli -h localhost -p 6379
   
   127.0.0.1:6379> AUTH tenant2-password
   OK
   127.0.0.1:6379> SET customer:100 "Tenant2 Customer"
   OK
   127.0.0.1:6379> GET customer:100
   "Tenant2 Customer"
   ```

3. **Re-connect as Tenant 1 and verify:**
   ```bash
   redis-cli -h localhost -p 6379
   
   127.0.0.1:6379> AUTH tenant1-password
   OK
   127.0.0.1:6379> GET customer:100
   "Tenant1 Customer"  # Still sees their own value
   ```

**Expected Result:** Each tenant sees only their own data for same key name

---

### Scenario 4: Cross-shard Operations

**Objective:** Test behavior with keys on different shards

**Steps:**

1. **Insert keys that will hash to different slots:**
   ```bash
   redis-cli -h localhost -p 6379
   
   127.0.0.1:6379> SET product:A "Product A"
   OK
   127.0.0.1:6379> SET product:B "Product B"
   OK
   127.0.0.1:6379> SET product:C "Product C"
   OK
   ```

2. **Try cross-shard MGET:**
   ```bash
   127.0.0.1:6379> MGET product:A product:B product:C
   
   # Expected: Either succeeds (Camellia handles it) or error
   # If error: "ERR CROSSSLOT Keys in request don't hash to the same slot"
   ```

3. **Try set operations across shards:**
   ```bash
   127.0.0.1:6379> SADD set1 "member1"
   (integer) 1
   127.0.0.1:6379> SADD set2 "member2"
   (integer) 1
   127.0.0.1:6379> SINTER set1 set2
   
   # Expected: Error - use hash tags for cross-key set operations
   # (error) ERR CROSSSLOT ...
   ```

4. **Retry with hash tags:**
   ```bash
   127.0.0.1:6379> SADD {mysets}:set1 "member1"
   (integer) 1
   127.0.0.1:6379> SADD {mysets}:set2 "member2" 
   (integer) 1
   127.0.0.1:6379> SINTER {mysets}:set1 {mysets}:set2
   (empty array)  # Success - both sets on same shard
   ```

**Expected Result:** 
- Cross-shard multi-key ops may fail depending on Camellia config
- Hash tags enable same-shard operations

---

### Scenario 5: Config Hot Reload

**Objective:** Verify Camellia picks up Dashboard config changes

**Steps:**

1. **Check current routing for tenant-1:**
   ```bash
   redis-cli -h localhost -p 6379
   
   127.0.0.1:6379> AUTH tenant1-password
   OK
   127.0.0.1:6379> SET test:key "original_pool"
   OK
   ```

2. **Update Dashboard config (change tenant-1 to use Pool 2):**
   ```bash
   curl -X POST "http://localhost:8080/camellia/admin/resourceTable/createOrUpdate" \
     -H "Content-Type: application/json" \
     -d '{
       "bid": 1,
       "bgroup": "service-group-1",
       "resourceTable": "{\"type\":\"simple\",\"operation\":{\"resource\":\"redis-sentinel://@10.1.20.101:26379,.../master-pool2?password=...\"}}"
     }'
   ```

3. **Wait 5-10 seconds (Camellia poll interval)**

4. **Insert new key and verify routing:**
   ```bash
   127.0.0.1:6379> SET test:key2 "new_pool"
   OK
   ```

5. **Check which pool has the new key:**
   ```bash
   # Check Pool 2 (new config)
   redis-cli -h 10.1.20.10 -p 6379 -a pool2-redis-password GET test:key2
   "new_pool"  # Should be here now
   
   # Check Pool 1 (old config)
   redis-cli -h 10.1.10.10 -p 6379 -a pool1-redis-password GET test:key2
   (nil)  # Not here
   ```

**Expected Result:** New keys route to updated pool after config reload

---

## 4. PERFORMANCE BENCHMARKING

### Benchmark 1: Throughput Test

**Using redis-benchmark:**

```bash
# Direct to Redis (baseline)
redis-benchmark -h 10.1.10.10 -p 6379 -a pool1-redis-password \
  -t get,set -n 100000 -c 50 -d 100 -q

# Results: ~150K GET/sec, ~120K SET/sec

# Through Camellia Proxy
redis-benchmark -h localhost -p 6379 -a tenant1-password \
  -t get,set -n 100000 -c 50 -d 100 -q

# Expected: ~140K GET/sec, ~110K SET/sec
# Overhead: ~5-10%
```

### Benchmark 2: Latency Test

```bash
# Latency through proxy
redis-cli -h localhost -p 6379 -a tenant1-password --latency

# Expected output:
# min: 0, max: 2, avg: 0.45 (1000 samples)
# Target: avg < 0.5ms, p99 < 2ms
```

### Benchmark 3: Pipeline Performance

**Test script:**
```python
import redis
import time

r = redis.Redis(host='localhost', port=6379, password='tenant1-password')

# Without pipeline
start = time.time()
for i in range(10000):
    r.set(f'bench:nopipe:{i}', f'value{i}')
elapsed_nopipe = time.time() - start

# With pipeline
pipe = r.pipeline()
start = time.time()
for i in range(10000):
    pipe.set(f'bench:pipe:{i}', f'value{i}')
pipe.execute()
elapsed_pipe = time.time() - start

print(f"No pipeline: {elapsed_nopipe:.2f}s ({10000/elapsed_nopipe:.0f} ops/sec)")
print(f"Pipeline: {elapsed_pipe:.2f}s ({10000/elapsed_pipe:.0f} ops/sec)")
print(f"Speedup: {elapsed_nopipe/elapsed_pipe:.2f}x")

# Expected: 5-10x speedup with pipeline
```

### Benchmark 4: Multi-tenant Concurrent Load

**Using memtier_benchmark:**

```bash
# Simulate 3 tenants with concurrent load
memtier_benchmark -s localhost -p 6379 -a tenant1-password \
  --threads=4 --clients=50 --requests=10000 --test-time=60 &

memtier_benchmark -s localhost -p 6379 -a tenant2-password \
  --threads=4 --clients=50 --requests=10000 --test-time=60 &

memtier_benchmark -s localhost -p 6379 -a tenant3-password \
  --threads=4 --clients=50 --requests=10000 --test-time=60 &

wait

# Check for any tenant experiencing degradation
# All tenants should have similar latency profiles
```

---

## 5. TROUBLESHOOTING GUIDE

### Issue 1: Connection Refused

**Symptom:**
```
redis.exceptions.ConnectionError: Error connecting to localhost:6379.
```

**Solutions:**
1. Verify Camellia Proxy is running:
   ```bash
   netstat -tulpn | grep 6379
   # Or
   lsof -i :6379
   ```

2. Check proxy logs:
   ```bash
   tail -f /var/log/camellia/proxy.log
   ```

3. Verify firewall:
   ```bash
   sudo ufw status
   sudo ufw allow 6379/tcp
   ```

---

### Issue 2: Authentication Errors

**Symptom:**
```
redis.exceptions.AuthenticationError: Authentication failed
```

**Solutions:**
1. Verify password mapping in Dashboard:
   ```bash
   curl http://localhost:8080/camellia/admin/resourceTable/list
   # Check bid/bgroup for your password
   ```

2. Test with correct password format:
   ```bash
   redis-cli -h localhost -p 6379
   127.0.0.1:6379> AUTH tenant1-password
   ```

3. Check proxy authentication config:
   ```yaml
   # application.yml
   camellia-redis-proxy:
     password: default  # Fallback password
     transpond:
       dynamic: true  # Must be enabled for multi-tenant
   ```

---

### Issue 3: Keys Not Found After Insert

**Symptom:**
```
127.0.0.1:6379> SET mykey "value"
OK
127.0.0.1:6379> GET mykey
(nil)
```

**Solutions:**
1. Check if you're using correct tenant:
   ```bash
   # Did you re-authenticate after connection?
   127.0.0.1:6379> AUTH tenant1-password
   OK
   127.0.0.1:6379> GET mykey
   ```

2. Verify backend Redis pools are healthy:
   ```bash
   redis-cli -h 10.1.10.10 -p 6379 -a pool1-redis-password PING
   redis-cli -h 10.1.20.10 -p 6379 -a pool2-redis-password PING
   ```

3. Check Camellia proxy can reach Sentinels:
   ```bash
   redis-cli -h 10.1.10.101 -p 26379 SENTINEL master master-pool1
   ```

---

### Issue 4: Cross-shard MGET Fails

**Symptom:**
```
127.0.0.1:6379> MGET key1 key2 key3
(error) ERR CROSSSLOT Keys in request don't hash to the same slot
```

**Solutions:**
1. Use hash tags to force same slot:
   ```bash
   127.0.0.1:6379> MSET {user}:key1 v1 {user}:key2 v2 {user}:key3 v3
   OK
   127.0.0.1:6379> MGET {user}:key1 {user}:key2 {user}:key3
   1) "v1"
   2) "v2"
   3) "v3"
   ```

2. Or check if Camellia cross-shard support is enabled:
   ```yaml
   # Some Camellia configs may support cross-shard transparently
   # Check documentation for your version
   ```

---

### Issue 5: Dashboard Config Not Applied

**Symptom:** Config changes in Dashboard don't reflect in proxy behavior

**Solutions:**
1. Check proxy poll interval:
   ```yaml
   # application.yml
   camellia-redis-proxy:
     transpond:
       remote:
         check-interval-millis: 5000  # 5 seconds
   ```

2. Force manual reload:
   ```bash
   # Restart proxy (will pick up latest config)
   systemctl restart camellia-proxy
   ```

3. Verify Dashboard API returns config:
   ```bash
   curl "http://localhost:8080/camellia/admin/resourceTable/get?bid=1&bgroup=service-group-1"
   ```

4. Check proxy logs for config updates:
   ```bash
   tail -f /var/log/camellia/proxy.log | grep "config update"
   ```

---

## APPENDIX A: Quick Reference

### Hash Slot Calculation (Python)
```python
def calculate_hash_slot(key: str) -> int:
    import hashlib
    # Extract hash tag if present
    start = key.find('{')
    if start != -1:
        end = key.find('}', start + 1)
        if end != -1 and end > start + 1:
            hash_key = key[start + 1:end]
        else:
            hash_key = key
    else:
        hash_key = key
    
    crc = 0xFFFF
    for byte in hash_key.encode('utf-8'):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    
    return crc % 1024
```

### Common Redis Commands for Testing
```bash
# String operations
SET key value
GET key
INCR counter
MGET key1 key2 key3
MSET key1 val1 key2 val2

# Hash operations
HSET hash field value
HGET hash field
HGETALL hash

# Set operations (use hash tags!)
SADD {set}:1 member
SINTER {set}:1 {set}:2

# Pipeline
redis-cli --pipe < commands.txt

# Monitor traffic
redis-cli MONITOR
```

---

## APPENDIX B: Test Coverage Matrix

| Feature | Test ID | Automated | Manual | Priority |
|---------|---------|-----------|--------|----------|
| Hash slot calculation | TC-201 | ✓ | ✓ | P1 |
| Consistent hashing | TC-203 | ✓ | - | P1 |
| Distribution uniformity | TC-208 | ✓ | - | P1 |
| Hash tag routing | TC-204 | ✓ | ✓ | P1 |
| Basic routing | TC-201 | ✓ | ✓ | P1 |
| MGET same shard | TC-101 | ✓ | ✓ | P1 |
| MGET cross-shard | TC-102 | ✓ | ✓ | P1 |
| SCAN cross-shard | TC-215 | ✓ | - | P2 |
| Tenant auth | TC-301 | ✓ | ✓ | P1 |
| Tenant isolation | TC-302/303 | ✓ | ✓ | P1 |
| Tenant routing | TC-306 | ✓ | ✓ | P1 |
| Pipeline perf | TC-114 | ✓ | ✓ | P1 |
| Transactions | TC-115 | ✓ | ✓ | P2 |
| Config hot reload | - | - | ✓ | P1 |
| Throughput | - | - | ✓ | P1 |
| Latency | - | - | ✓ | P1 |

**Legend:**
- ✓ = Covered
- - = Not covered
- P1 = High priority
- P2 = Medium priority

---

END OF DOCUMENTATION
