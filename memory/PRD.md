# Syroce PMS — Product Requirements Document

## System Overview
Hotel PMS + Channel Manager platform. FastAPI backend, MongoDB, Redis. Multi-tenant architecture with OTA/provider integrations (Exely, HotelRunner). Outbox pattern, import/ingest pipelines, idempotency protections. AES-256-GCM encryption with AAD binding.

## Core Architecture
- `/app/backend/` — FastAPI backend
- `/app/backend/controlplane/` — OPS-001 Control Plane module
- `/app/backend/core/` — Core services (outbox, import bridge, crypto, secrets)
- `/app/backend/channel_manager/` — Channel manager adapters
- `/app/backend/workers/` — Background workers (ARI push, retry, etc.)
- `/app/backend/tests/resilience/` — Chaos testing and resilience validation suite
- `/app/backend/docs/BATTLE_READINESS_BLUEPRINT.md` — Battle-grade execution blueprint
- `/app/frontend/src/pages/ControlPlane.jsx` — Control Plane UI (ops weapon)

## Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Completed Features

### OPS-001: Production-Grade Control Plane
- Core module at `/app/backend/controlplane/`
- Failure taxonomy (5 types: RETRYABLE, PERMANENT, PROVIDER_ERROR, DATA_ERROR, SECURITY_ERROR)
- 15 API endpoints under `/api/ops/*`
- Idempotent retry engine with dry-run support
- Alerting engine with cooldowns and webhook support
- 14 operational runbooks
- Startup validator
- 38 unit tests + 29 API tests (all passing)

### CHAOS-001: Chaos Testing & Resilience Validation Program
- Comprehensive 10-part strategy document (`CHAOS_TESTING_MASTER_PLAN.md`)
- 69 resilience tests across 7 test files — all passing
- Test categories: Provider failures, Worker failures, Retry/Replay safety, Crypto resilience, Tenant isolation, Ops visibility, Burst/Soak
- Game day plan, automation strategy, pilot readiness checklist

### BATTLE-GRADE EXECUTION BLUEPRINT (2026-02-15)
- 10-section production evolution blueprint (`BATTLE_READINESS_BLUEPRINT.md`, 2576 lines)
- Covers all sections from Dashboard to Learning Loop
- Concrete data models, API contracts, workflows, failure modes, metrics
- 30-day week-by-week execution roadmap with Go/No-Go criteria

### CORE BATTLE LOOP (2026-03-22) — Week 1 MVP
Implementation of the "minimum battle loop" — the three systems that make the platform visible:

#### 1. Event Timeline System
- **Collection**: `event_timeline` with 5 indexes (entity, correlation, external_id, stage_health, TTL 90d)
- **TimelineWriter** (`controlplane/timeline_writer.py`): Fire-and-forget event appender, never blocks main flow
- **TimelineReader** (`controlplane/timeline_reader.py`): Read + gap detection + stuck event finder
- **Timeline API** (`controlplane/timeline_router.py`): 7 endpoints under `/api/ops/timeline/*`
  - `GET /api/ops/timeline/external/{external_id}` — Primary debug entry point
  - `GET /api/ops/timeline/correlation/{correlation_id}` — Full flow trace
  - `GET /api/ops/timeline/{entity_type}/{entity_id}` — Entity timeline
  - `GET /api/ops/timeline/search` — Search with filters
  - `GET /api/ops/timeline/gaps` — Stuck event detection
  - `GET /api/ops/timeline/raw-payload/{correlation_id}` — Raw webhook payload
  - `GET /api/ops/timeline/raw-payloads/by-external/{external_id}` — All raw payloads for a reservation
- **Performance**: Traces reservation in <1 second (goal was <5 seconds)

#### 2. FailureTracker Wiring
- **import_bridge_service.py**: On failure records structured failure to `cp_failures` + timeline event
- **outbox_worker.py**: On permanent failure records to `cp_failures` + timeline event

#### 3. Minimal Dashboard (Read-Only)
- **DashboardAggregator** (`controlplane/dashboard_aggregator.py`): 8 parallel queries, health score algorithm
- **DashboardSnapshotWorker**: Stores time-series snapshots every 60s in `cp_health_snapshots`
- **Dashboard API** (`controlplane/dashboard_router.py`): 5 endpoints under `/api/ops/dashboard/*`

### WEBHOOK TIMELINE INTEGRATION (2026-03-22) — End-to-End Traceability
Completed the "last 20%" — wiring the Event Timeline into OTA webhook entry points for true end-to-end tracing:

#### 1. Exely Webhook Timeline
- **Modified**: `providers/exely/exely_webhook_router.py`
- Timeline stages: `webhook_received` → `normalized` → `deduplicated`
- Raw SOAP XML payload stored in `webhook_raw_payloads` collection

#### 2. HotelRunner Webhook Timeline
- **Modified**: `providers/hotelrunner_webhook.py`
- Timeline stages: `webhook_received` → `deduplicated` → `normalized` → `validated`
- Raw JSON payload stored in `webhook_raw_payloads` collection

#### 3. Ingest Pipeline Timeline
- **Modified**: `domains/channel_manager/ingest/pipeline.py`
- Timeline stages written at: duplicate detection, stale detection, normalization, mapping validation

#### 4. Raw Payload Storage
- **Collection**: `webhook_raw_payloads` with 4 indexes (correlation, tenant+ext, provider, TTL 90d)

### CONTROL PLANE UI (2026-03-22) — Operations Weapon
Frontend operations screen that turns developer APIs into a self-service debugging tool:

#### 1. Reservation Trace (Trace tab)
- **File**: `/app/frontend/src/pages/ControlPlane.jsx` — `ReservationLookup` component
- Input: external_id or correlation_id
- Output: Status badge (PROCESSING/CONFIRMED/FAILED/DUPLICATE), full timeline, gap warnings
- Timeline events expandable with metadata JSON
- ROOM OK/ROOM FAIL badges on validated events
- Raw Payload viewer for webhook_received events
- Copy-to-clipboard for IDs

#### 2. System Health (Saglik tab)
- **Component**: `SystemHealth`
- Health grade (A-F) with score
- Metric cards: Import Basari, Sync Basari, Outbox Bekleyen, Hatalar (24s)
- Pipeline depth: ingest_pending → import_pending → outbox_pending
- Recent failures list
- Auto-refresh every 30 seconds

#### 3. Live Feed (Canli tab)
- **Component**: `LiveFeed`
- Last 50 events in table: Zaman, Stage, External ID, Provider, Durum
- Auto-refresh toggle (10s interval)
- Failure events highlighted in red
- Manual refresh button

#### Route & Navigation
- Route: `/control-plane`
- Nav: Kanallar dropdown → Control Plane

## Pending Tasks

### P1 — Hardening (from Blueprint Week 2)
- Implement immutable folio_ledger + reconciliation engine
- Implement key rotation (data model + API + ReEncryptionWorker)
- PMS battle tests (split reservation, no-show, room change, overbooking, cancellation)
- Implement Learning Loop (IncidentClassifier, recurrence detection, never-again rules)

### P1 — Stress + Exposure (from Blueprint Week 3)
- Reservation Burst test (15K reservations)
- ARI Storm test (120K updates)
- Provider Downtime simulation
- Pilot hotel shadow mode + canary rollout

### P2 — Tech Debt
- Fix pre-existing test failures
- Fix pre-existing lint errors
- Legacy file cleanup (~80 files in backend/ root)
- ~264 legacy db imports to tenant-scoped access

## Bug Fixes

### Navigation Module Visibility Bug (2026-03-22)
- **Root Cause**: `isModuleEnabled()` in `Layout.js` treated undefined module keys as disabled. Login response `tenant.modules` only contained `{"pms": true, "reports": true}`, causing all other modules (reservation_calendar, channel_manager, night_audit, etc.) to be hidden from navigation.
- **Fix**: Changed logic to `modules[moduleKey] !== false` — only explicitly disabled modules are hidden; undefined keys are treated as enabled.
- **File**: `/app/frontend/src/components/Layout.js`
