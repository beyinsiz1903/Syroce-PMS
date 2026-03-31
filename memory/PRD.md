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
1. Transition Phase Bar — 4-phase progress: Shadow -> Dry-Run -> Limited -> Full Live
2. Write Readiness Score — 0-100 circular gauge with component breakdown
3. Provider Health Panel
4. Operational Actions
5. Sync Overview
6. Failure Visibility
7. Recent Events
8. Recent Drifts
9. Operations Breakdown
10. Shadow Observation Alerts
11. Observation History

### Phase 6 — P1 Shadow Observation & Write Path Plan [2026-03-30]
- `observation.py` — Daily snapshot collection, alert thresholds, ingest consistency
- `readiness.py` — Write Readiness Score (0-100) weighted composite
- `transition.py` — 4-phase transition plan with entry/exit/rollback criteria

### Phase 7 — P1 Dry-Run Write Path [2026-03-30]
- `dry_run.py` — Full dry-run write engine: production-identical path, NO-OP external calls
- Failure simulation (timeout, validation_error, rate_limit)
- Create/Modify/Cancel chain test
- Write Enable Criteria (6 criteria)

### Phase 8 — P1 Shadow Automation (Celery Beat) [2026-03-30]
- 6-hourly periodic snapshots
- Daily summary generation
- Alert rules (readiness_low, drift_high, dlq_nonempty, auth_failure, dry_run_chain_fail)
- Retention: snapshots 30d, summaries 90d, alerts 60d
- Dashboard: Shadow Otomasyon panel, 4 trend panels
- Redis + Celery Worker + Beat via Supervisor

### Phase 9 — E2E Reservation Test Suite [2026-03-31]
Full sentetik test akisi via mock server (34/34 PASSED):

**Altyapi:**
- Mock credentials stored for test-tenant (isolated from prod namespace)
- Room mappings (DLX, STD, SUI, FAM) and rate plan mappings (BAR, PROMO, RACK, NONREF) created
- Feature flags: connector_enabled=true, shadow_mode=true, write_enabled=false

**Test Zincirleri:**
- Connection Test (auth -> channels -> rooms -> reservations)
- Pull Reservations (with date/status filters)
- Ingest Chain: New -> Modify -> Cancel (full pipeline)
- Duplicate Rejection (same provider_event_id skip)
- Stale Update Rejection (same payload_hash skip)
- Trace Timeline (5+ raw events per reservation)
- Confirm Delivery (idempotent ACK)
- Dry-Run ARI Push (mode=dry_run, success)
- Dry-Run Chain (create->modify->cancel, all steps pass)
- Failure Simulation (timeout, rate_limit, validation_error -> correct error_category tracking)
- Dry-Run Stats (39 runs, 74.4% success rate)
- Write Criteria (3/6 met)
- Ops Dashboard (all panels populated)
- Observation Snapshot + Automation Trigger
- Final Safety: shadow_mode=true, write_enabled=false

**Test Command:**
```bash
cd /app/backend && python -m pytest tests/test_e2e_reservation_flow.py -v --tb=short
```

## API Endpoints (v2 Connector)

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/channel/hotelrunner-v2/status | Connector health + metrics |
| GET | /api/channel/hotelrunner-v2/ops-dashboard | Aggregated ops dashboard |
| GET | /api/channel/hotelrunner-v2/trace/{id} | Reservation timeline trace |
| POST | /api/channel/hotelrunner-v2/test-connection | Connection smoke test |
| POST | /api/channel/hotelrunner-v2/pull-reservations | Pull reservations |
| POST | /api/channel/hotelrunner-v2/ingest | Ingest single reservation |
| POST | /api/channel/hotelrunner-v2/push-ari | ARI push (with verification) |
| POST | /api/channel/hotelrunner-v2/confirm-delivery | Confirm delivery to HR |
| GET | /api/channel/hotelrunner-v2/verify-transaction/{id} | Verify ARI transaction |
| POST | /api/channel/hotelrunner-v2/reconcile | Trigger reconciliation |
| GET | /api/channel/hotelrunner-v2/reconciliation/history | Past runs |
| GET | /api/channel/hotelrunner-v2/reconciliation/drifts | Recent drifts |
| GET | /api/channel/hotelrunner-v2/flags | Get feature flags |
| PUT | /api/channel/hotelrunner-v2/flags | Update feature flags |
| GET | /api/channel/hotelrunner-v2/metrics | Metrics summary |
| GET | /api/channel/hotelrunner-v2/dlq | Dead letter queue |
| POST | /api/channel/hotelrunner-v2/dlq/{id}/retry | Retry DLQ entry |
| GET | /api/channel/hotelrunner-v2/readiness-score | Write Readiness Score |
| POST | /api/channel/hotelrunner-v2/observation/snapshot | Collect snapshot |
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
| GET | /api/channel/hotelrunner-v2/automation/status | Automation status |
| POST | /api/channel/hotelrunner-v2/automation/trigger | Manual snapshot trigger |
| GET | /api/channel/hotelrunner-v2/automation/trends | Trend data |
| GET | /api/channel/hotelrunner-v2/automation/alerts | Alert history |
| POST | /api/channel/hotelrunner-v2/automation/alerts/acknowledge | Alert ACK |
| GET | /api/channel/hotelrunner-v2/automation/daily-summaries | Daily summaries |

### Phase 10 — Room Mapping UI [2026-03-31]
- Full Eşlemeler tab: HotelRunner rooms ↔ PMS room types mapping
- Backend: GET /pms-room-types, GET /cached-rooms, POST /room-mappings/bulk
- Upsert logic, bulk save, delete, new PMS type creation
- Visual: Green "Eşlendi" badge, amber unmapped warning, summary bar
- 9/9 pytest tests passing

## Upcoming Tasks

### P1 — 7-Day Shadow Observation (IN PROGRESS)
- Automated via Celery Beat (6h snapshots collecting data)
- Dashboard shows observation day count and history
- Pending: Wait for 7 days of data collection before evaluating write readiness

### P1 — Limited Live Write (UPCOMING)
- Single tenant / small scope live write execution
- Requires: Readiness score stable >=90, dry-run chain >=95%, DLQ=0, drift<5

### P1 — Full Live Write (UPCOMING)
- Full live write execution across all tenants
- Requires: Successful limited live period + all 6 write criteria green

### P2 — PII Phase 3: Strict Mode Enforcement
### P2 — Wire failure tracking
### P2 — App.jsx Decomposition (2100+ lines)
### P3 — Legacy HR connector migration/cleanup
