# Load Test Framework Configuration
# This file documents load profiles, thresholds, and scenario configurations.

## Load Profiles

### Normal Business Day
- VUs: 20
- Duration: 5 min
- Arrival Rate: 5/s
- Mix: 40% dashboard, 30% booking ops, 20% audit, 10% mobile

### Morning Checkout Surge
- VUs: 50, ramping to 100
- Duration: 3 min burst
- Focus: departures, folio, rooms
- Threshold: p95 < 2s

### OTA Reservation Burst
- VUs: ramping 5 -> 100 -> 5
- Duration: 40s
- Focus: booking creation, room availability, conflict detection
- Threshold: error rate < 15%, p95 < 3s

### ARI Storm
- VUs: ramping 10 -> 200 -> 10
- Duration: 30s
- Focus: pricing reads, forecast, compset
- Threshold: error rate < 10%, p95 < 4s

### Night Audit Overlap
- VUs: 15 sustained + 5 audit runners
- Duration: 60s
- Focus: audit history, business date, metrics, exceptions
- Threshold: p95 < 5s

### Degraded Provider Mode
- Simulated: External API timeouts
- VUs: 20
- Duration: 30s
- Focus: channel manager retries, circuit breaker, fallback

## Measured Metrics

| Metric | Source | Threshold |
|--------|--------|-----------|
| p50/p95/p99 latency | k6 http_req_duration | p95 < 3s |
| Error rate | k6 custom rate | < 10% |
| Queue lag | API /metrics/operational | < 5s |
| Worker backlog growth | API /metrics/operational | Stable |
| WebSocket event latency | k6 ws_poll_latency | p95 < 2s |
| Reconciliation recovery | ARI storm -> read consistency | < 10s |
| Drift detection latency | Channel manager | < 30s |
| Dashboard data freshness | System health API | < 5s stale |
| Rate limit hit frequency | 429 status codes | < 5% |
| Tenant isolation breach | Negative test cross-tenant | 0 |

## Running

### k6
```sh
# Single scenario
k6 run load_tests/ota_reservation_burst.js

# With env override
k6 run -e BASE_URL=https://pms.example.com load_tests/night_audit_load.js

# All scenarios
for f in load_tests/*.js; do k6 run "$f"; done
```

### Locust
```sh
# Headless
locust -f load_tests/locust_pms.py --headless -u 50 -r 5 -t 60s --host http://localhost:8001

# Web UI
locust -f load_tests/locust_pms.py --host http://localhost:8001
```

## Failure Interpretation

| Failure Pattern | Root Cause | Action |
|----------------|------------|--------|
| p95 spike > 5s | DB query without index | Add compound index |
| Error rate > 15% | Connection pool exhaustion | Increase pool / add circuit breaker |
| Queue lag growing | Worker saturation | Scale workers / add backpressure |
| WS latency spike | Event bus contention | Switch to Redis pub/sub |
| 429 cluster | Rate limit too aggressive | Tune rate limiter per-tenant |
| Cross-tenant data | Tenant filter missing | Fix query / add middleware check |
