# CAMELLIA REDIS - COMPREHENSIVE TEST SUITE
# ==========================================

> Note: Tài liệu này chứa một phần nội dung cũ từ bộ test Sentinel/dashboard tổng quát. Repo hiện tại dùng các file test đang tồn tại trong `1-proxy-only/`, `2-with-dashboard/`, và stress tool `../scripts/stress_test.py`.

## 📦 Package Contents

This test suite provides comprehensive testing for Camellia Redis Proxy with focus on:
- ✅ Sharding & Routing
- ✅ Multi-tenancy & Isolation
- ✅ Performance Benchmarking
- ✅ Hash Tag Support

### Files Included

```
📁 camellia-redis-test-suite/
├── 📊 camellia_redis_test_plan.xlsx      # Complete test plan (135 test cases)
├── 🐍 1-proxy-only/test_proxy_core.py    # Proxy core test
├── 🐍 1-proxy-only/test_proxy_standalone.py # Standalone/shared-auth test
├── 🐍 2-with-dashboard/test_dashboard_integration.py # Dashboard integration test
├── ⚙️  camellia_dashboard_config.txt     # Dashboard configuration
├── 📖 TEST_SCENARIOS.md                   # Detailed test scenarios & guide
├── 🐍 ../scripts/stress_test.py           # Service-aware stress tool
└── 📄 README.md                            # This file
```

---

## 🚀 QUICK START

### Prerequisites

**Infrastructure Requirements:**
- Camellia Proxy running (default: localhost:6379)
- Camellia Dashboard API (default: http://localhost:8080)
- 10 Redis Sentinel Pools configured
- Python 3.8+

**Python Dependencies:**
```bash
pip install redis requests
```

### 1️⃣ Configure Dashboard (One-time Setup)

Extract and run the setup script from `camellia_dashboard_config.txt`:

```bash
# Configure 3 test tenants
curl -X POST "http://localhost:8080/camellia/admin/resourceTable/createOrUpdate" \
  -H "Content-Type: application/json" \
  -d @tenant1_config.json

curl -X POST "http://localhost:8080/camellia/admin/resourceTable/createOrUpdate" \
  -H "Content-Type: application/json" \
  -d @tenant2_config.json

# ... (see config file for full setup)
```

### 2️⃣ Run Automated Tests

```bash
python test_camellia_sharding.py
```

**Expected Output:**
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║            CAMELLIA REDIS - SHARDING & MULTI-TENANCY TEST SUITE              ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

================================================================================
                   TEST SUITE 1: HASH SLOT CALCULATION & ROUTING
================================================================================

[TC-201] Hash slot calculation verification
✓ PASS: Full key hashing: 'user:1000' -> slot 342 (hashed: 'user:1000')
✓ PASS: Hash tag extraction: '{user}:1000' -> slot 529 (hashed: 'user')
...

TEST SUMMARY
Total Tests: 13
Passed: 13
Failed: 0
Pass Rate: 100.0%
```

### 3️⃣ Review Test Plan (Excel)

Open `camellia_redis_test_plan.xlsx` in Excel/LibreOffice:

- **Sheet 1**: Test Overview & Summary Dashboard
- **Sheets 2-7**: Detailed test cases (135 total)
- **Sheet 8**: Execution log
- **Sheets 9-10**: Reference documentation

---

## 📋 TEST COVERAGE

### Automated Tests (13 test cases)

| Category | Tests | Coverage |
|----------|-------|----------|
| Hash Calculation | 4 | CRC16, consistent hashing, distribution |
| Redis Operations | 4 | Routing, MGET/MSET, SCAN |
| Multi-tenancy | 3 | Auth, isolation, config |
| Advanced | 2 | Pipeline, transactions |

### Manual Test Scenarios (15+ scenarios)

See `TEST_SCENARIOS.md` for detailed step-by-step instructions:

1. ✅ Basic Sharding Verification
2. ✅ Hash Tag Routing
3. ✅ Multi-tenant Isolation
4. ✅ Cross-shard Operations
5. ✅ Config Hot Reload
6. ✅ Throughput Benchmarking
7. ✅ Latency Testing
8. ✅ Pipeline Performance
9. ✅ Multi-tenant Concurrent Load
10. And more...

### Full Test Plan (135 test cases)

The Excel file contains comprehensive test coverage:

- **Basic Commands**: 25 tests (GET, SET, HASH, LIST, SET, ZSET)
- **Multi-key Operations**: 15 tests (MGET, MSET, SINTER, etc.)
- **Sharding & Routing**: 20 tests (hash slots, distribution, SCAN)
- **Multi-tenancy**: 12 tests (auth, isolation, per-tenant config)
- **Rate Limiting**: 10 tests (per-tenant limits, enforcement)
- **Hot Key Caching**: 8 tests (cache hit, eviction)
- **Failover & HA**: 15 tests (Sentinel failover, proxy HA)
- **Performance**: 10 tests (QPS, latency, overhead)
- **Security**: 8 tests (auth, IP filtering, command blocking)
- **Operations**: 12 tests (config reload, pool management)

---

## 🎯 KEY FEATURES TESTED

### 1. Sharding & Routing

**Hash Slot Calculation:**
- CRC16 algorithm (Redis Cluster standard)
- 1024 buckets (configurable)
- Consistent hashing for stable routing

**Hash Tag Support:**
```redis
# All keys route to same shard
SET {user}:profile "data"
SET {user}:settings "data"
SET {user}:history "data"

# Enable MGET across related keys
MGET {user}:profile {user}:settings {user}:history
```

**Distribution Verification:**
- 10,000 key uniformity test
- Validates ±20% deviation tolerance
- Statistical analysis included

### 2. Multi-tenancy

**Password-based Tenant Routing:**
```python
# Tenant 1 connects with tenant1-password
# → Routes to Pool 1

# Tenant 2 connects with tenant2-password  
# → Routes to Pool 2

# Complete data isolation
```

**Per-tenant Configuration:**
- Dedicated pool assignment
- Sharding configuration
- Rate limiting
- IP whitelisting

**Isolation Testing:**
```redis
# Tenant 1
AUTH tenant1-password
SET customer:100 "Tenant1 Data"

# Tenant 2
AUTH tenant2-password
SET customer:100 "Tenant2 Data"

# Each sees only their own data
```

### 3. Performance Benchmarking

**Throughput Targets:**
- GET: 100K QPS
- SET: 80K QPS
- Mixed workload: 150K QPS

**Latency Targets:**
- Average: <0.5ms
- P99: <2ms
- Proxy overhead: <5%

**Pipeline Performance:**
- Expected: 5-10x speedup
- Test: 10,000 commands pipelined

---

## 📊 USING THE EXCEL TEST PLAN

### Test Execution Workflow

**Step 1: Plan**
- Open `Sheet 1: Test Overview`
- Review test categories and counts
- Assign testers

**Step 2: Execute**
- Navigate to relevant test sheet (e.g., `Sheet 3: Sharding & Routing`)
- For each test case:
  - Execute the command/procedure
  - Record actual result
  - Update status (Pass/Fail/Blocked)
  - Add notes if needed

**Step 3: Track**
- Excel auto-calculates pass rates
- Summary dashboard updates automatically
- Use `Sheet 8: Execution Log` to track multiple test runs

**Step 4: Report**
- Summary shows overall health
- Color-coded status indicators:
  - 🟢 Green: Pass Rate ≥95%
  - 🟡 Yellow: Pass Rate 80-95%
  - 🔴 Red: Pass Rate <80%

### Formulas Included

The Excel file contains 39 formulas for automatic calculation:

```excel
# Pass Rate
=IF(B12=0, 0, C12/B12)

# Not Run Count
=B12-C12-D12-E12

# Overall Status
=IF(G12>=0.95, "PASS", IF(G12>=0.8, "WARNING", "FAIL"))
```

All formulas verified with zero errors ✅

---

## 🔧 TROUBLESHOOTING

### Common Issues

**1. Connection Refused**
```
Error: redis.exceptions.ConnectionError
```
**Solution:** Verify Camellia Proxy is running on port 6379

**2. Authentication Failed**
```
Error: redis.exceptions.AuthenticationError
```
**Solution:** Check Dashboard password mapping for tenant

**3. Cross-shard MGET Fails**
```
Error: ERR CROSSSLOT Keys in request don't hash to the same slot
```
**Solution:** Use hash tags: `MGET {user}:key1 {user}:key2`

**4. Config Not Applied**
```
Dashboard updated but proxy still uses old config
```
**Solution:** Wait 5-10 seconds for proxy poll interval

See `TEST_SCENARIOS.md` Section 5 for complete troubleshooting guide.

---

## 📈 BENCHMARK EXAMPLES

### Throughput Test

```bash
# Through Camellia Proxy
redis-benchmark -h localhost -p 6379 -a tenant1-password \
  -t get,set -n 100000 -c 50 -d 100 -q

Results: SET: 110450.22 requests per second
         GET: 138696.25 requests per second
```

### Latency Test

```bash
redis-cli -h localhost -p 6379 -a tenant1-password --latency

min: 0, max: 2, avg: 0.45 (1000 samples)
```

### Pipeline Test

```python
# Without pipeline: 5.32s (1880 ops/sec)
# With pipeline: 0.58s (17241 ops/sec)
# Speedup: 9.17x ✓
```

---

## 🎓 LEARNING RESOURCES

### Understanding Hash Tags

**Purpose:** Route related keys to same shard for multi-key operations

**Syntax:**
```redis
# Hash tag in curly braces
{user}:profile      # Hashes "user"
{user}:settings     # Hashes "user" → Same shard

# Multiple tags - first one wins
{user}:{session}:data  # Hashes "user"

# No tag - hash full key
user:profile        # Hashes "user:profile"
```

**Use Cases:**
- MGET/MSET multiple keys
- Set operations (SINTER, SUNION)
- Sorted set operations (ZINTER)
- Transactions (MULTI/EXEC)

### Understanding CRC16 Hashing

The test suite implements Redis Cluster's CRC16 algorithm:

```python
def calculate_crc16(key: str) -> int:
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
```

**Properties:**
- 16-bit output (0-65535)
- Modulo 1024 → slot (0-1023)
- Consistent for same input
- Uniform distribution

---

## 📞 SUPPORT & FEEDBACK

### Running Into Issues?

1. **Check Prerequisites**
   - Camellia Proxy running?
   - Dashboard accessible?
   - Python dependencies installed?

2. **Review Logs**
   - Proxy logs: `/var/log/camellia/proxy.log`
   - Dashboard logs: `/var/log/camellia/dashboard.log`

3. **Consult Documentation**
   - `TEST_SCENARIOS.md` - Detailed scenarios
   - `camellia_dashboard_config.txt` - Config reference

4. **Test Incrementally**
   - Start with automated tests
   - Move to manual scenarios
   - Benchmark last

### Test Results Tracking

Use the Excel file's execution log to track:
- Multiple test runs (Lab → Staging → Production)
- Pass rate trends
- Blocker/failure patterns
- Duration tracking

---

## 📝 VERSION HISTORY

**v1.0.0** (Current)
- Initial release
- 135 test cases across 10 categories
- Automated test suite (13 tests)
- 15+ manual test scenarios
- Performance benchmarking guide
- Complete troubleshooting documentation

---

## 🎉 NEXT STEPS

1. ✅ **Setup Environment** - Configure Dashboard with test tenants
2. ✅ **Run Automated Tests** - Validate basic functionality
3. ✅ **Execute Manual Scenarios** - Deep-dive into features
4. ✅ **Benchmark Performance** - Establish baselines
5. ✅ **Track Results** - Use Excel to monitor progress

**Happy Testing! 🚀**

---

## APPENDIX: Quick Command Reference

```bash
# Run automated tests
python test_camellia_sharding.py

# Connect to proxy
redis-cli -h localhost -p 6379

# Authenticate as tenant
AUTH tenant1-password

# Test routing
SET {user}:test "value"
GET {user}:test

# Benchmark throughput
redis-benchmark -h localhost -p 6379 -a tenant1-password -n 100000

# Monitor latency
redis-cli -h localhost -p 6379 -a tenant1-password --latency

# Check proxy stats (if console enabled)
redis-cli -h localhost -p 16379 INFO

# Configure Dashboard (example)
curl -X POST "http://localhost:8080/camellia/admin/resourceTable/createOrUpdate" \
  -H "Content-Type: application/json" \
  -d @config.json
```

---

**Documentation Version:** 1.0.0  
**Last Updated:** 2026-03-30  
**Test Suite:** Camellia Redis - Production Grade
