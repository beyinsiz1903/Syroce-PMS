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
Full sentetik test akisi via mock server (34/34 PASSED)

### Phase 10 — Room Mapping UI [2026-03-31]
- Full Eslemeler tab: HotelRunner rooms <-> PMS room types mapping
- Backend: GET /pms-room-types, GET /cached-rooms, POST /room-mappings/bulk
- 9/9 pytest tests passing

### Bug Fix — Test Room Data Cleanup [2026-03-31]
- Removed 78 test rooms (TEST999, TEST_*, BULK_*, DELTEST_*, UPD_*) from MongoDB
- These were leftovers from automated testing (testing agent bulk create/delete tests)
- Calendar now shows only 30 real rooms (Standard:8, Deluxe:8, Superior:6, Suite:4, Family:2, Junior Suite:2)

### Bug Fix — Orphaned Test Bookings Cleanup [2026-03-31]
- Removed 138 test/fake unassigned bookings (TestGuest*, ParseTest*, TenantTest*, AutoImport*, source=ota_sandbox)
- "113 atanmamis oda" indicator reduced to "3 atanmamis oda" (3 real no-show bookings remain)
- Database relational integrity restored

### Feature — Unassigned Bookings Panel [2026-03-31]
- "Atanmamis oda" button in calendar header is now clickable
- Opens a slide-in panel from the right showing all unassigned active reservations
- Panel shows guest name, booking ID, dates, room type, status, and amount
- Clicking a booking in the panel opens the Reservation Detail Modal
- Panel closes via X button or backdrop click
- Files: CalendarHeader.jsx, ReservationCalendar.jsx

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
