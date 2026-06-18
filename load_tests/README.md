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

## POS F&B - Birincil Yuk Hedefi (PRIMARY)

`load_tests/pos_fnb_burst.js` artik salt-okuma degil; **gercek v2 POS yazma
dongusunu** (create order -> close/odeme -> open-tab cekismesi) + okuma
karisimini surer. Yeni 6 POS index'ini yuk altinda dogrular:

| Index | Koleksiyon | Surulen yol |
|-------|-----------|-------------|
| `idx_pos_orders_status_created` (tenant_id,status,created_at) | pos_orders | active-orders panosu |
| `idx_pos_orders_tenant_created` (tenant_id,created_at) | pos_orders | dashboard / rapor range |
| `tenant_id_1_id_1` (tenant_id,id) | pos_orders | close_order kaynak lookup |
| `tenant_id_1_id_1` (tenant_id,id) | pos_transactions | islem lookup |
| `idx_pos_txn_tenant_order` (tenant_id,order_id) | pos_transactions | close_order txn lookup |
| `idx_pos_txn_open_tab` PARTIAL {status:open} (tenant_id,outlet_id,table_number) | pos_transactions | open_tab dup guard |

### Doktrin (mutlak)
- SADECE stress tenant'ina yazar. `demo@hotel.com` / pilot tenant reddedilir
  (setup fail-closed; `pilot_drift=0`).
- Tum yazmalar `POS_LOAD_PREFIX`'i `guest_name` + `table_number` +
  `idempotency_key` alanlarina basar -> kosu sonrasi tek komutla temizlenir.
- `post_to_folio=false` (folyo/Xchange yan-etkisi YOK). Sentetik PII.
- **Bu testi AGENT calistirmaz**; operator deploy'a karsi dispatch eder.

### Zorunlu env (fail-closed)
`BASE_URL`, `E2E_STRESS_ADMIN_EMAIL`, `E2E_STRESS_ADMIN_PASSWORD`,
`E2E_STRESS_TENANT_ID`, `POS_LOAD_PREFIX` (>=4 char). Opsiyonel:
`POS_OUTLET_ID` (varsayilan `<prefix>OUTLET`).

Backend tarafinda da: `E2E_ALLOW_DESTRUCTIVE_STRESS=true` ve (varsa)
`PILOT_TENANT_ID` set (cleanup gate stack icin).

### Esikler
- `pos_read_latency_ms` p95 < 1500ms
- `pos_create_latency_ms` p95 < 2500ms
- `pos_close_latency_ms` p95 < 3000ms
- `pos_tab_latency_ms` p95 < 3000ms
- `pos_unexpected_errors` rate < 0.02  (ASIL kapi: 5xx + beklenmeyen 4xx)
- `pos_tab_conflict_409` / `pos_throttle_429`: gozlem sayaclari (409=beklenen
  contention, 429=throttle; ASIL hata oranina KARISTIRILMAZ).

### Dispatch (operator, deploy'a karsi)
```sh
PREFIX="POSLOAD_$(date +%Y%m%d%H%M%S)_"
k6 run \
  -e BASE_URL=https://<deploy-domain> \
  -e E2E_STRESS_ADMIN_EMAIL="$E2E_STRESS_ADMIN_EMAIL" \
  -e E2E_STRESS_ADMIN_PASSWORD="$E2E_STRESS_ADMIN_PASSWORD" \
  -e E2E_STRESS_TENANT_ID="$E2E_STRESS_TENANT_ID" \
  -e POS_LOAD_PREFIX="$PREFIX" \
  load_tests/pos_fnb_burst.js
```

### Cleanup (kosu sonrasi ZORUNLU) + idempotency
Prefix-scoped, fail-closed dedicated endpoint. data_prefix = az once kullanilan
`$PREFIX`.
```sh
# cleanup #1 -> silinen sayilar > 0 beklenir
curl -sS -X POST https://<deploy-domain>/api/admin/stress/pos-load-cleanup \
  -H "Authorization: Bearer $SUPER_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"target_tenant_id\":\"$E2E_STRESS_TENANT_ID\",\"data_prefix\":\"$PREFIX\"}"

# cleanup #2 -> AYNI komut; idempotency teyidi: tum deleted_counts == 0 olmali
```
Gate stack: super_admin + `target_tenant_id == E2E_STRESS_TENANT_ID` +
`PILOT_TENANT_ID` blok + `E2E_ALLOW_DESTRUCTIVE_STRESS=true`. `data_prefix`
bos/<4 char ise 400. audit_logs ASLA silinmez.

### IXSCAN teyidi (Atlas)
Kosu sirasinda/sonrasinda Atlas Profiler veya `$queryStats` ile yukaridaki
yollarin COLLSCAN degil **IXSCAN** kullandigini dogrula (ozellikle
active-orders, dashboard range, open_tab dup guard). Profiler'i sadece teyit
penceresinde ac, sonra kapat.

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
