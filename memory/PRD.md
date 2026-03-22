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

### Deploy Pipeline — Hard Gate CI/CD & Progressive Deploy (2026-03-22) — Phase 2
Production-grade deployment pipeline with hard gates, auto-rollback, migration verification, smoke tests, and canary analysis.

#### 1. Hard Gate CI/CD Pipeline
- **File**: `ops/deploy_pipeline.py`
- 6 sequential blocking gates: lint → unit_test → security_audit → migration_check → build → smoke_test
- Each gate MUST pass before the next runs (no `|| true`)
- Pipeline state persisted in MongoDB `deploy_pipelines` collection
- Gate runners execute real checks: ruff lint, pytest, security scan, schema drift, dependency validation, HTTP smoke tests

#### 2. Migration Verification System
- **File**: `ops/migration_verification.py`
- Schema drift detection against expected indexes (`REQUIRED_INDEXES`)
- Required collection existence check (`REQUIRED_COLLECTIONS`)
- Oversized collection warnings (>10M docs)
- Collection statistics: document counts, index counts

#### 3. Smoke Test Suite
- **File**: `ops/smoke_test_runner.py`
- 8 real HTTP tests: health (liveness, basic, db), auth login, rooms list, bookings list, guests list, settings
- Token extraction from login for authenticated endpoint testing
- Critical/non-critical classification
- Duration tracking per test

#### 4. Auto-Rollback Engine
- **File**: `ops/auto_rollback_engine.py`
- 5 real metric triggers: 5xx error rate (APM), health endpoint, DB ping, outbox backlog, import failures
- Threshold-based evaluation: `continue` / `pause` / `rollback` recommendations
- Rollback execution with post-rollback smoke test verification
- Evaluation and rollback history in MongoDB

#### 5. Deploy Dashboard (Frontend)
- 5th tab "Deploy" added to Governance Panel at `/admin/governance`
- Pipeline gate status visualization with per-gate timing and errors
- Auto-rollback trigger cards showing real metric values vs thresholds
- Smoke test runner button with inline results
- Pipeline history view with status badges
- All elements with data-testid for automation

### Governance & Metering Layer (2026-03-22) — Phase 1
Full production governance stack: entitlement enforcement, usage metering, dynamic feature flags, and onboarding automation.

#### 1. Entitlement Enforcement Middleware
- **File**: `core/entitlement.py`
- Global ASGI middleware intercepting all `/api/*` requests
- Route-to-module mapping (`ROUTE_MODULE_MAP`): channel_manager, night_audit, invoices, revenue_management, ai, sales_crm, group_sales, loyalty_program, gm_dashboards
- Hard 403 block with `ENTITLEMENT_DENIED` error code + upgrade URL
- Exempt routes for auth, health, admin, settings, system endpoints
- Quota enforcement: `check_quota(tenant_id, "rooms"|"users")`
- Full entitlement view: `get_tenant_entitlements(tenant_id)` returns modules, quotas, plan limits, subscription status

#### 2. Usage Metering Service
- **File**: `core/metering.py`
- In-memory buffer with periodic flush (60s) to `usage_daily` collection
- 15 event types: `api_call`, `reservation_created`, `login`, `guest_created`, `channel_sync`, `report_generated`, `invoice_created`, `ai_request`, `webhook_received`, `night_audit_run`, etc.
- Tenant usage summary: daily/monthly aggregation with pipeline queries
- System-wide overview: today/month totals, active tenants (7d), top 10 tenants
- Metering hooks wired into: login endpoint, reservation creation service

#### 3. Dynamic Feature Flag Service
- **File**: `core/feature_flags.py`
- In-memory cache with 30s TTL, MongoDB-backed `feature_flags` collection
- Resolution order: kill_switch → expiry → tenant_override → rollout_percentage → enabled
- Deterministic hash-based percentage rollout per tenant
- Full CRUD: create, update, delete flags
- Tenant-specific overrides: set/remove per flag

#### 4. Onboarding Automation Engine
- **File**: `core/onboarding.py`
- 12-step default checklist covering: setup, operations, team, channels, finance, reports
- Auto-detection from MongoDB collections (rooms, guests, bookings, users, provider_configs, invoices, etc.)
- Module-aware: steps requiring disabled modules are excluded
- Manual step completion + progress reset
- System-wide onboarding overview for admin

#### 5. Admin API — 16 Endpoints
- **File**: `domains/admin/entitlement_router.py`
- Entitlements: overview, tenant detail, quota check
- Metering: system overview, tenant summary, tenant timeline
- Feature Flags: list, get, create/update, delete, tenant override, check
- Onboarding: overview, tenant progress, mark complete, reset

#### 6. Frontend — Governance Panel
- **File**: `pages/GovernancePanel.js`
- Route: `/admin/governance` (super_admin only)
- 4-tab interface: Entitlement, Metering, Feature Flags, Onboarding
- Entitlement tab: tier summary cards, tenant list with drill-down dialog (quotas, active/inactive modules)
- Metering tab: today/monthly usage, active tenants, top tenants leaderboard
- Feature Flags tab: flag CRUD, toggle, kill switch, rollout percentage, tenant overrides
- Onboarding tab: progress bars per tenant, drill-down checklist with circular progress indicator
- All elements have data-testid attributes

#### 7. Documentation
- **File**: `backend/docs/ONBOARDING_PLAYBOOK.md`
- Structured onboarding playbook: 5-10 day timeline, role assignments, success criteria
- Pilot KPI metrics: DAU, reservations/day, check-in time, error rate, channel sync, NPS
- Reference customer template with 30-day metrics format

**Test Coverage**: 28/28 backend tests passing, 4/4 frontend tabs verified
**Collections Created**: `usage_daily` (3 indexes), `feature_flags` (unique key), `onboarding_progress`

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

## Bug Fixes

### Navigation Module Visibility Bug (2026-03-22)
- **Root Cause**: `isModuleEnabled()` in `Layout.js` treated undefined module keys as disabled. Login response `tenant.modules` only contained `{"pms": true, "reports": true}`, causing all other modules (reservation_calendar, channel_manager, night_audit, etc.) to be hidden from navigation.
- **Fix**: Changed logic to `modules[moduleKey] !== false` — only explicitly disabled modules are hidden; undefined keys are treated as enabled.
- **File**: `/app/frontend/src/components/Layout.js`

### Past Date Reservation Bug (2026-03-22)
- **Root Cause**: `tenant_settings.business_date` was stuck at `2026-03-14` because the night audit was blocked. Both frontend and backend used this stale business date as the minimum allowed reservation date, allowing bookings for past dates (March 14-21).
- **Fix**: Changed validation to use `max(business_date, today)` — ensures past dates are always blocked even when business date is stale.
- **Files Modified**:
  - `/app/frontend/src/pages/ReservationCalendar.js` — `handleCellClick` and `handleCreateBooking` functions
  - `/app/frontend/src/pages/calendar/CalendarDialogs.js` — `min` attribute on check-in date inputs
  - `/app/frontend/src/components/calendar/CalendarDialogs.js` — `min` attribute on check-in date input
  - `/app/backend/modules/reservations/services/create_reservation_service.py` — Backend date validation


### Enterprise Codebase Cleanup (2026-03-22)
- **Root-level junk files:** 10 empty files deleted (`1000`, `99%`, `=`, `NOT`, `READY`, `processing`, `repository`, `service`, `confirm`, `Payment button in the Rooms tab.`)
- **Orphan test scripts:** 7 files deleted from `/app/` root (moved to proper test infrastructure)
- **Version drift fixed:** README.md updated — React 18→19, Python 3.8→3.11, Node.js 16→20, MongoDB→7.0+
- **Frontend README:** CRA boilerplate replaced with proper project documentation
- **Unused dependencies removed:** `@apollo/client`, `graphql`, `file-saver`, `react-is`, `cra-template`
- **Legacy backend files:** 67 orphan `.py` files quarantined to `/app/backend/_legacy/`
- **Router registry cleanup:** 18 dead `_OPTIONAL_ROUTERS` entries removed from `bootstrap/router_registry.py`

## Pending Tasks

### P0 — Governance Layer Phase 2 (Feature Flag Governance)
- Dynamic Feature Flags with percentage rollout ~~(DONE in Phase 1)~~
- Flag Admin API + UI ~~(DONE in Phase 1)~~
- Middleware integration with entitlement ~~(DONE in Phase 1)~~

### P0 — Governance Layer Phase 3 (Support Tooling)
- Support Dashboard: tenant health overview, quick actions (extend sub, toggle module, view logs)
- Impersonate tenant (view-as-tenant for debugging)
- Audit log viewer per tenant
- Ticket/note system per tenant

### P0 — Governance Layer Phase 4 (Pilot KPI Dashboard)
- Adoption rate tracking per tenant (DAU, feature usage)
- Feature usage heatmap
- Error rate per tenant timeline
- Response time percentiles per tenant
- Export/report generation
- Reference customer evidence template UI

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
- ~~Fix pre-existing test failures~~ **DONE (2026-03-22)** — Converted 3 middleware to pure ASGI, rewrote hardening tests, curated CI suite (304 tests)
- ~~Fix pre-existing lint errors~~ **DONE (2026-03-22)** — Pipeline lint gate uses project's pyproject.toml ruff config, passes clean
- ~~Legacy file cleanup (~80 files in backend/ root)~~ **DONE (2026-03-22)** — 67 files moved to `_legacy/`, 18 legacy router refs removed from `router_registry.py`
- ~264 legacy db imports to tenant-scoped access

### P2 — Enhancements
- Ctrl+K shortcut for quick Trace lookup
- Login endpoint to return full module list (prevent future nav bugs)
