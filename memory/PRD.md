# Syroce PMS — Product Requirements Document

## Original Problem Statement
Full-stack hotel PMS (Property Management System) application with multi-tenant architecture, booking management, room inventory, channel management, and CI/CD pipeline.

## Architecture
- **Frontend:** React (Vite 8 + Rolldown) with Shadcn/UI, TailwindCSS, Recharts
- **Backend:** FastAPI (Python) with MongoDB (motor async driver)
- **Database:** MongoDB
- **CI/CD:** GitHub Actions with curated test suite

## Core Features Implemented
- Multi-tenant booking management with atomic room-night locking
- Room type system with inventory management
- Channel manager integration (Exely, HotelRunner)
- Hold/OOO (Out of Order) room management
- AI Chatbot for hotel operations
- Audit trail & timeline events
- Crypto engine for sensitive data
- Outbox pattern for reliable event publishing
- Comprehensive battle test suite (540+ tests)
- Channel Health Management Dashboard (with historical trends + field KPIs)

## What's Been Completed

### Channel Health Management Dashboard v2 (2026-03-23)
- **Upgraded from pilot screen to management screen**
- **Historical Trends API:** New `/api/ops/dashboard/channel-health/trends` endpoint
  - Time-bucketed push latency (p50/p95/p99) with auto bucket sizing
  - Sync success rate time series
  - Drift creation count time series
  - Retry success rate time series
  - Failure count time series
- **Field KPIs API:** New `/api/ops/dashboard/channel-health/field-kpis` endpoint
  - Sync success rate (period-over-period comparison)
  - Drift reduction tracking
  - MTTR (Mean Time To Resolve) for reconciliation issues
  - Operator intervention count
  - Push SLA compliance percentage
- **Frontend:** Complete redesign of `ChannelHealthDashboard.jsx`
  - Recharts trend line/area/bar charts
  - 5 field KPI cards with delta/trend indicators
  - Time period selector (24h, 3d, 7d, 30d)
  - Auto-refresh every 60s
- **Testing:** 20/20 backend + 14/14 frontend tests passed

### Environment Variable Unification (2026-03-23)
- **Replaced all `REACT_APP_BACKEND_URL` → `VITE_BACKEND_URL`**
  - 123 backend test files updated
  - 1 ops/deploy_pipeline.py updated
  - CI/CD workflow (ci-cd.yml) updated
  - Docker Compose files (3 files) updated
  - Frontend README.md updated
  - Zero remaining references in codebase

### Channel Health Dashboard v1 (2026-03-23)
- **Backend:** `/api/ops/dashboard/channel-health` endpoint with 6 aggregation pipelines
- **Frontend:** KPI strip, latency bars, failure breakdown, drift cards, provider SLA

### Documentation & Quality Hardening (2026-03)
- README drift fixed, Security snapshot, Test health section
- Channel Capability Matrix, Pilot KPI Framework
- deploy.yml fixed (graceful-skip pattern)
- ADR-002 updated, Quarantine README updated

### Quarantine Test Restoration (2026-03-23)
- 7 quarantined test files restored, 10 individually skipped tests fixed
- Test count: 391+ CI tests, 0 failures

### CI/CD Pipeline Stability
- Frontend build fix (.js -> .jsx for Vite 8/Rolldown)
- Flaky test fix, yarn audit handling, deployment fix

## P0 — Completed
- [x] Frontend production build (Vite 8/Rolldown compatibility)
- [x] Flaky backend test stabilization
- [x] CI/CD pipeline reliability
- [x] Quarantine test restoration
- [x] CI/CD deployment jobs (graceful-skip pattern)
- [x] Documentation drift resolution
- [x] Channel Health Dashboard v1 (KPI strip + detail)
- [x] Channel Health Management Dashboard v2 (historical trends + field KPIs)
- [x] Environment variable unification (REACT_APP_BACKEND_URL → VITE_BACKEND_URL)

## P1 — Upcoming
- [ ] Fix remaining quarantined tests: stale_fixtures (rate_manager, 10 tests)
- [ ] Fix remaining quarantined tests: changed_api (10 tests)
- [ ] Fix remaining quarantined tests: changed_implementation (13 tests)
- [ ] Channel manager inventory ledger alignment with room-type system
- [ ] Exely/HotelRunner sandbox testing (per capability matrix gaps)
- [ ] CI/CD actual deployment logic (Docker build/push, Kubernetes manifests)

## P2 — Backlog
- [ ] Fix remaining quarantined tests: external_dependency (3 tests)
- [ ] Crypto Migration (SEC-002)
- [ ] Secrets Management Rollout (SEC-001)
- [ ] Enable Strict Tenant Mode
- [ ] motor -> pymongo native async migration
- [ ] Production build with Nginx static serving
- [ ] ~264 legacy DB import cleanup
- [ ] Governance Phase 3-4 (Support/KPI Dashboard)
- [ ] Push latency SLO monitoring (per capability matrix)
- [ ] Rate parity monitoring dashboard
- [ ] Pilot hotel onboarding (per KPI framework)

## Key Technical Decisions
- **Vite 8 `.jsx` Convention:** All React component files use `.jsx` extension for Rolldown compatibility.
- **Test Isolation:** Battle tests use `random.randint(2100, 9999)` for date ranges + session-scoped DB cleanup.
- **Quarantine Fix Pattern:** Far-future dates (3000-6000 day offsets), sync pymongo for DB verification.
- **yarn audit CI Gate:** Uses bitmask check `(exit_code & 24) != 0` to only fail on HIGH/CRITICAL.
- **Deploy graceful-skip:** All deploy jobs check for secrets existence before attempting deployment.
- **Channel Health Aggregator:** MongoDB aggregation pipelines with $lookup, $dateTrunc for time bucketing, linear interpolation for percentiles.
- **Field KPIs:** Period-over-period comparison (current vs previous period of same length).
- **Environment Variables:** `VITE_BACKEND_URL` is the single source of truth for backend URL across all environments (frontend, backend tests, CI/CD, Docker).

## Key API Endpoints
- `GET /api/ops/dashboard/channel-health` — Current period health metrics
- `GET /api/ops/dashboard/channel-health/trends` — Historical time-series data
- `GET /api/ops/dashboard/channel-health/field-kpis` — Operational field KPIs with comparison

## Test Credentials
| User | Email | Password | Role |
|:---|:---|:---|:---|
| Demo Admin | demo@hotel.com | demo123 | super_admin |
