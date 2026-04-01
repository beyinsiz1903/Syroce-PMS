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

### Phase 6 — P1 Shadow Observation & Write Path Plan [2026-03-30]
- `observation.py` — Daily snapshot collection, alert thresholds, ingest consistency
- `readiness.py` — Write Readiness Score (0-100) weighted composite
- `transition.py` — 4-phase transition plan with entry/exit/rollback criteria

### Phase 7 — P1 Dry-Run Write Path [2026-03-30]
- `dry_run.py` — Full dry-run write engine: production-identical path, NO-OP external calls

### Phase 8 — P1 Shadow Automation (Celery Beat) [2026-03-30]
- 6-hourly periodic snapshots, daily summaries, alert rules, Redis + Celery

### Phase 9 — E2E Reservation Test Suite [2026-03-31]
Full sentetik test akisi via mock server (34/34 PASSED)

### Phase 10 — Room Mapping UI [2026-03-31]
- Full Eslemeler tab: HotelRunner rooms <-> PMS room types mapping
- Backend: GET /pms-room-types, GET /cached-rooms, POST /room-mappings/bulk

### Bug Fix — Test Room & Booking Cleanup [2026-03-31]
- Removed 78 test rooms and 138 fake bookings from MongoDB
- Calendar shows only 30 real rooms

### Feature — Unassigned Bookings Panel [2026-03-31]
- "Atanmamis oda" button in calendar header is now clickable
- Opens a slide-in panel showing all unassigned active reservations
- Clicking a booking opens the Reservation Detail Modal

### Feature — Virtual Room System + No-Show Management [2026-04-01]
- Created 6 virtual rooms (V-STD, V-DLX, V-SUP, V-STE, V-JST, V-FAM), one per room type
- Virtual rooms excluded from calendar, dashboard stats, and cache by default
- API: `POST /api/pms/bookings/no-show-virtual` — marks booking as no-show and assigns to virtual room
- API: `GET /api/pms/rooms/virtual` — lists virtual rooms
- API: `POST /api/pms/rooms/virtual/seed` — creates virtual rooms for all room types
- API: `GET /api/pms/rooms?include_virtual=true` — includes virtual rooms in listing
- No-Show button added to unassigned bookings panel (marks as no-show + assigns to virtual room)
- Night audit: confirmed-unassigned bookings do NOT block day close (only checked_in without room blocks)

### Feature — Rate Manager Provider Push Status [2026-04-01]
- API: `GET /api/channel-manager/rate-manager/push-providers` — returns all channel provider statuses
- Rate Manager page now shows badges for each provider with mode status
- All 9 backend tests passed (iteration 170)

### Feature — No-Show Reason + Analytics [2026-04-01]
- `POST /api/pms/bookings/no-show-virtual` now accepts `no_show_reason` field
- API: `GET /api/pms/no-show-analytics?days=30` — returns daily counts, room type breakdown, channel breakdown, reason breakdown, revenue loss, recent records
- New page: `/no-show-analytics` -> `frontend/src/pages/NoShowAnalytics.jsx`
- No-Show reason dialog added to calendar unassigned panel
- All 12 backend + frontend tests passed (iteration 171)

### Feature — Advanced No-Show & Revenue Analytics [2026-04-01]
**4 new analytics tabs added to No-Show Analytics page:**

#### 1. Channel Loss Analytics (FULL)
- API: `GET /api/pms/channel-loss-analytics?days=30`
- Kanal bazli: no-show count, total loss, avg loss, no-show rate (%)
- Top 3 worst channels with detailed cards
- Channel trend over time (stacked bar chart)
- Data quality/confidence indicator

#### 2. Overbooking Heatmap (FULL)
- API: `GET /api/pms/overbooking-heatmap?days=90`
- Date-based color-coded heatmap grid
- Top 5 riskiest days (peak days)
- Weekly pattern (weekend vs weekday)
- Channel contribution overlay
- Data quality/confidence indicator

#### 3. Rule Engine (LIGHT)
- APIs: `GET/POST /api/pms/alert-rules`, `DELETE/PATCH .../toggle`, `POST .../evaluate`, `GET .../history`
- Alert/suggestion mode only (Shadow Mode — no automatic writes)
- CRUD for rules with metrics: overbooking_count, noshow_count, noshow_rate
- Actions: rate_dusur, prepaid_zorunlu, kanal_kapat, manuel_inceleme
- Trigger history tracking
- Evaluation against current data

#### 4. No-Show Prediction (BASIC)
- API: `GET /api/pms/noshow-prediction?days_ahead=7`
- Rule-based prediction: risk score (0-100)
- Risk levels: Low/Medium/High
- Factors: channel rate, day-of-week pattern, amount
- Historical rates by channel and day-of-week
- Data quality/confidence indicator
- Future ML-ready feature store design

**Files Created:**
- `/app/backend/routers/pms_analytics.py` — 4 new API endpoints
- `/app/frontend/src/pages/NoShowAnalytics.jsx` — Redesigned with 4 tabs
- All 24 backend + frontend tests passed (iteration 172)

### Bug Fix — Exely Connection Restore [2026-04-01]
- Exely connection was accidentally disconnected on 2026-03-30 during HotelRunner v2 setup
- Connection reactivated (`is_active: true`)
- `room_types` and `rate_plans` restored from existing `exely_room_mappings` data
- 3 room types (Standart, Deluxe, Suite) + 3 rate plans restored
- Rate Manager page now shows room types correctly

### Bug Fix — pms_analytics.py Lint Errors [2026-04-01]
- Fixed import ordering (I001)
- Fixed 3x set comprehension (C401) — `set(... for ...)` -> `{... for ...}`

### Bug Fix — Exely 500 Error Root Cause & Fix [2026-04-01]
- **Root Cause**: SOAP Security header format was wrong. Code used full WSSE (oasis) headers but WSDL requires simple attribute-based `<Security Username="..." Password="..." />` in the PMSConnect namespace.
- **Additional Issue**: Stored credentials were invalid (`test_invalid_user`/`test_pass`/`hotel_code=12345`). Updated with real Exely credentials (`PMSConnect.501694`/`hotel_code=501694`).
- **Fix**: Rewrote `_soap_envelope()` in `soap_builder.py` to use attribute-based Security header per WSDL schema. Updated default endpoint URL to `/api/PMSConnect.svc`. Updated credentials in secrets manager and `exely_connections` collection.
- **Result**: All SOAP calls now return HTTP 200 successfully. 3 room types + 5 rate plans discovered from live API.

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

### P2 — "Otomatik Esle" (Auto-Map) Feature Enhancement
### P2 — PII Phase 3: Strict Mode Enforcement
### P2 — Wire failure tracking
### P2 — App.jsx Decomposition (2100+ lines)
### P3 — Legacy HR connector migration/cleanup

## Notes
- Exely API 500 error RESOLVED (2026-04-01) — was caused by wrong SOAP Security header format + invalid credentials
- HotelRunner v2 connector running in Shadow Mode (write_enabled=false)
- PMS has 6 room types but only 3 mapped to Exely (Superior, Junior Suite, Family not yet mapped)
