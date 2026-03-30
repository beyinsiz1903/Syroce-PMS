# Syroce PMS — Product Requirements Document

## Overview
Multi-tenant SaaS PMS + Channel Manager + Control Plane.
Canonical data model: Reservation, Inventory, Rate, Restriction.
Architecture: Outbox pattern, reconciliation, idempotent ingest, observability.

## Core Architecture
- **Backend**: FastAPI + MongoDB + Redis + Celery
- **Frontend**: React + Vite
- **Deployment**: Docker Compose (nginx, backend, worker, beat, mongo, redis)
- **Security**: KMS encryption, secret classification, rotation lifecycle, PII protection

## Completed Features

### Phase 1 — Auth + Credential Security
- SecretManager / credential vault
- KMS encryption integration
- Token rotation support

### Phase 2 — Mock + Read/Write Path E2E
- Mock HotelRunner server (port 9999)
- Ingest pipeline (webhook/pull -> validate -> dedup -> map -> persist -> trace)
- ARI outbound (outbox pattern)
- 27/27 tests passed

### CSP Fix for /api/redoc
- Nginx + FastAPI middleware CSP headers fixed
- Production deployment verified

### Phase 3 — HotelRunner v2 Connector (Production-Grade) [2026-03-30]
New connector: `backend/channel_manager/connectors/hotelrunner_v2/`

**Architecture:**
- `endpoint_map.py` — v1/v2 mixed path mapping (per HR docs)
- `client.py` — Async HTTP client (httpx, typed responses, error taxonomy)
- `mapper.py` — Bi-directional mapper matching REAL HR API format
- `errors.py` — Error taxonomy (auth, validation, rate_limit, timeout, server, parse)
- `retry.py` — Exponential backoff (max 5, jitter) + Dead Letter Queue
- `service.py` — Business logic orchestration + transaction verification
- `feature_flags.py` — Tenant-based flags (enabled, shadow_mode, write_enabled, dry_run_mode, limited_scope)
- `metrics.py` — Operational metrics (success rate, latency, error taxonomy)
- `reconciliation.py` — PMS vs HR comparison, drift detection, auto-fix
- `router.py` — REST API (25+ endpoints under /api/channel/hotelrunner-v2/)

### Phase 4 — P0 Live Production Test [2026-03-30]
- Successfully tested all endpoints against real HotelRunner production API
- Auth, rooms, reservations, channels verified
- Shadow mode stable, DLQ empty, no errors

### Phase 5 — P1 Ops Dashboard Frontend [2026-03-30]
New page: `/hrv2-ops` -> `frontend/src/pages/HRv2OpsDashboard.jsx`

**Panels:**
1. **Transition Phase Bar** — 4-phase progress: Shadow -> Dry-Run -> Limited -> Full Live
2. **Write Readiness Score** — 0-100 circular gauge with component breakdown (drift, error rate, retry, DLQ, latency)
3. **Provider Health Panel** — Auth status, Reservations API, Shadow Mode, Write Path, Son Pull, Latency, DLQ, Retry count
4. **Operational Actions** — Baglanti Testi, Reconciliation, Provider Durumu Yenile, Gunluk Snapshot Topla, Feature Flags
5. **Sync Overview** — Drift count, success rate, total operations, last reconciliation
6. **Failure Visibility** — Error taxonomy, DLQ entries
7. **Recent Events** — Last 10 connector events
8. **Recent Drifts** — Drift entries with severity
9. **Operations Breakdown** — Table with all operation metrics
10. **Shadow Observation Alerts** — Alert thresholds evaluation (ok/warn/critical)
11. **Observation History** — 7-day observation progress table with trends

### Phase 6 — P1 Shadow Observation & Write Path Plan [2026-03-30]

**New Backend Modules:**
- `observation.py` — Daily snapshot collection, alert thresholds, ingest consistency (duplicate/stale), daily reports
- `readiness.py` — Write Readiness Score (0-100) weighted composite: drift(25%), error_rate(25%), retry(15%), dlq(15%), latency(20%)
- `transition.py` — 4-phase transition plan with entry/exit/rollback criteria, state tracking, logging

**New API Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/channel/hotelrunner-v2/readiness-score | Write Readiness Score (0-100) |
| POST | /api/channel/hotelrunner-v2/observation/snapshot | Collect daily observation snapshot |
| GET | /api/channel/hotelrunner-v2/observation/history | Snapshot history (7 days) |
| GET | /api/channel/hotelrunner-v2/observation/report | Daily report with trends |
| GET | /api/channel/hotelrunner-v2/observation/thresholds | Alert threshold definitions |
| GET | /api/channel/hotelrunner-v2/transition/plan | Full 4-phase transition plan |
| GET | /api/channel/hotelrunner-v2/transition/status | Current phase + readiness |
| GET | /api/channel/hotelrunner-v2/transition/history | Transition log entries |

### Phase 7 — P1 Dry-Run Write Path [2026-03-30]

**New Backend Module:**
- `dry_run.py` — Full dry-run write engine: production-identical path, NO-OP external calls, failure simulation, chain test, write enable criteria

**New API Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/channel/hotelrunner-v2/dry-run/ari-push | Dry-run ARI push (NO-OP) |
| POST | /api/channel/hotelrunner-v2/dry-run/confirm-delivery | Dry-run confirm delivery |
| POST | /api/channel/hotelrunner-v2/dry-run/chain | Create/Modify/Cancel chain |
| POST | /api/channel/hotelrunner-v2/dry-run/simulate-failure | Failure scenario trigger |
| GET | /api/channel/hotelrunner-v2/dry-run/results | Execution history |
| GET | /api/channel/hotelrunner-v2/dry-run/stats | Success rate & failure breakdown |
| GET | /api/channel/hotelrunner-v2/dry-run/write-criteria | Write enable criteria check |

**Frontend Updates:**
- Dry-Run Kontrol panel (ARI Push, Chain Test, Failure Simulation buttons)
- Dry-Run Hata Dagilimi panel (failure breakdown by category)
- Write Acma Kriterleri panel (6 criteria: readiness>=90, drift<5, dry-run rate>=95%, DLQ=0, retry<5, chain success)

## API Endpoints (v2 Connector)

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/channel/hotelrunner-v2/status | Connector health + metrics |
| GET | /api/channel/hotelrunner-v2/ops-dashboard | Aggregated ops dashboard (incl. readiness + transition) |
| GET | /api/channel/hotelrunner-v2/trace/{id} | Reservation timeline trace |
| POST | /api/channel/hotelrunner-v2/test-connection | Connection smoke test |
| POST | /api/channel/hotelrunner-v2/pull-reservations | Pull reservations |
| POST | /api/channel/hotelrunner-v2/ingest | Ingest single reservation |
| POST | /api/channel/hotelrunner-v2/push-ari | ARI push (with verification) |
| POST | /api/channel/hotelrunner-v2/confirm-delivery | Confirm delivery to HR |
| GET | /api/channel/hotelrunner-v2/verify-transaction/{id} | Verify ARI transaction |
| POST | /api/channel/hotelrunner-v2/reconcile | Trigger reconciliation |
| GET | /api/channel/hotelrunner-v2/reconciliation/history | Past reconciliation runs |
| GET | /api/channel/hotelrunner-v2/reconciliation/drifts | Recent drift entries |
| GET | /api/channel/hotelrunner-v2/flags | Get feature flags |
| PUT | /api/channel/hotelrunner-v2/flags | Update feature flags |
| GET | /api/channel/hotelrunner-v2/metrics | Metrics summary |
| GET | /api/channel/hotelrunner-v2/dlq | Dead letter queue |
| POST | /api/channel/hotelrunner-v2/dlq/{id}/retry | Retry DLQ entry |
| GET | /api/channel/hotelrunner-v2/readiness-score | Write Readiness Score |
| POST | /api/channel/hotelrunner-v2/observation/snapshot | Collect daily snapshot |
| GET | /api/channel/hotelrunner-v2/observation/history | Observation history |
| GET | /api/channel/hotelrunner-v2/observation/report | Daily report |
| GET | /api/channel/hotelrunner-v2/observation/thresholds | Alert thresholds |
| GET | /api/channel/hotelrunner-v2/transition/plan | Transition plan |
| GET | /api/channel/hotelrunner-v2/transition/status | Phase status |
| GET | /api/channel/hotelrunner-v2/transition/history | Transition log |
| POST | /api/channel/hotelrunner-v2/dry-run/ari-push | Dry-run ARI push |
| POST | /api/channel/hotelrunner-v2/dry-run/confirm-delivery | Dry-run confirm delivery |
| POST | /api/channel/hotelrunner-v2/dry-run/chain | Create/modify/cancel chain |
| POST | /api/channel/hotelrunner-v2/dry-run/simulate-failure | Failure simulation |
| GET | /api/channel/hotelrunner-v2/dry-run/results | Dry-run history |
| GET | /api/channel/hotelrunner-v2/dry-run/stats | Success rate & breakdown |
| GET | /api/channel/hotelrunner-v2/dry-run/write-criteria | Write enable criteria |

## Upcoming Tasks

### P1 — 7-Day Shadow Observation (IN PROGRESS)
- Daily snapshot collection via /observation/snapshot
- Monitor auth stability, pull trends, drift count
- Alert thresholds active (drift, error, retry, DLQ, latency, auth, duplicates, stale)
- 7-day goal: zero critical alerts, readiness score >= 80
- NEXT: Automate with Celery beat

### P1 — Dry-Run Write Path (COMPLETED)
- Simulated write pipeline with NO-OP external calls
- Transaction verification (read-only)
- Failure simulation (timeout, validation_error, rate_limit)
- Create/Modify/Cancel chain test
- Write Enable Criteria (6 criteria: readiness>=90, drift<5, dry-run rate>=95%, DLQ=0, retry<5, chain success)
- Dashboard integration: success rate, failure breakdown, last result, correlation trace

### P1 — Shadow Automation (NEXT)
- Celery beat ile gunluk snapshot otomasyonu
- Drift trend izleme
- Readiness score history

### P2 — PII Phase 3: Strict Mode Enforcement
### P2 — Wire failure tracking
### P2 — App.jsx Decomposition (2100+ lines)
### P3 — Legacy HR connector migration/cleanup
