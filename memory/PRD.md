# Syroce PMS — Product Requirements Document

## Original Problem Statement
Full-stack hotel PMS (Property Management System) application with multi-tenant architecture, booking management, room inventory, channel management, and CI/CD pipeline.

## Architecture
- **Frontend:** React (Vite 8 + Rolldown) with Shadcn/UI, TailwindCSS
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
- Channel Health Dashboard in Control Plane

## What's Been Completed

### Channel Health Dashboard (2026-03-23)
- **Backend:** New `/api/ops/dashboard/channel-health` endpoint with 6 aggregation pipelines
  - Push latency percentiles (p50/p95/p99) from `cm_rate_push_metrics`
  - Sync success rate per provider from `cm_sync_jobs`
  - Failure breakdown by category (timeout/validation/mapping/auth/provider)
  - Reconciliation drift count from `cm_reconciliation_issues`
  - Retry success rate from rate push metrics
  - Provider-based SLA compliance scoring
- **Frontend:** New "Kanal Sagligi" tab in Control Plane (`ControlPlane.jsx`)
  - KPI summary strip (latency, sync rate, drift count, retry rate)
  - Push latency distribution bars with p50/p95/p99
  - Stacked failure breakdown chart with color-coded categories
  - Reconciliation drift cards per provider with issue type breakdown
  - Provider SLA compliance cards (compliant/warning/breached)
  - Provider sync detail section with success/failure/duration metrics
  - Auto-refresh every 60s + manual refresh button
- **Files:** `channel_health_aggregator.py`, `ChannelHealthDashboard.jsx`, `ControlPlane.jsx`
- **Testing:** 12/12 backend tests passed, 10/10 frontend elements verified

### Documentation & Quality Hardening (2026-03)
- **README drift fixed:** `REACT_APP_BACKEND_URL` -> `VITE_BACKEND_URL` in Quick Start and Environment Variables
- **Security current status snapshot:** Added to README and CHANGELOG top — single source of truth for "nihai guncel sayi"
- **Test health section:** Added to README with T0/T1/T2 breakdown, quarantine visibility as controlled debt
- **Channel Capability Matrix:** `backend/docs/CHANNEL_CAPABILITY_MATRIX.md` — Exely/HotelRunner provider parity with gap analysis
- **Pilot KPI Framework:** `backend/docs/PILOT_KPI_FRAMEWORK.md` — 5 KPI categories, graduation criteria, design-vs-live gap analysis
- **deploy.yml fixed:** All `exit 1` TODO placeholders replaced with graceful-skip on missing secrets
- **deploy.yml env var fix:** `REACT_APP_BACKEND_URL` -> `VITE_BACKEND_URL` in frontend build-args
- **ADR-002 updated:** Current quarantine numbers (37 remaining), restoration log (70+ restored)
- **Quarantine README updated:** Current status table, restored files noted

### Quarantine Test Restoration (2026-03-23)
- **7 fully quarantined test files restored** to `tests/` from `_quarantine/`
- **10 individually skipped tests fixed** in-place
- **Root causes fixed:** async/sync mismatch, stale dates, stale room locks, stale fixtures
- **Test count: 391+ CI tests, 0 failures**

### CI/CD Pipeline Stability
- Frontend build fix (`.js` -> `.jsx` for Vite 8/Rolldown)
- Flaky test fix (wider `_RUN_TAG` random range)
- `yarn audit` bitmask-based exit code handling
- CI env vars (`VITE_BACKEND_URL`)
- Deployment fix (graceful skip when secrets not configured)

## P0 — Completed
- [x] Frontend production build (Vite 8/Rolldown compatibility)
- [x] Flaky backend test stabilization
- [x] CI/CD pipeline reliability
- [x] Quarantine test restoration (7 files + 10 individual tests)
- [x] CI/CD deployment jobs (deploy.yml graceful-skip pattern)
- [x] Documentation drift resolution (README, CHANGELOG, ADR-002)
- [x] Channel Health Dashboard in Control Plane (push latency p50/p95/p99, sync success rate, failure breakdown, reconciliation drift, retry success rate, provider SLA)

## P1 — Upcoming
- [ ] Fix remaining quarantined tests: stale_fixtures (rate_manager, 10 tests)
- [ ] Fix remaining quarantined tests: changed_api (10 tests)
- [ ] Fix remaining quarantined tests: changed_implementation (13 tests)
- [ ] Channel manager inventory ledger alignment with room-type system
- [ ] Exely/HotelRunner sandbox testing (per capability matrix gaps)
- [ ] CI/CD actual deployment logic (Docker build/push, Kubernetes manifests)

## P2 — Backlog
- [ ] Fix remaining quarantined tests: external_dependency (3 tests)
- [ ] Backend test env var unification (REACT_APP_BACKEND_URL -> VITE_BACKEND_URL)
- [ ] Crypto Migration (SEC-002) — will fix crypto v2 tests
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
- **Quarantine Fix Pattern:** Far-future dates (3000-6000 day offsets), sync pymongo for DB verification in sync tests, cleanup-before-seed for fixture isolation.
- **yarn audit CI Gate:** Uses bitmask check `(exit_code & 24) != 0` to only fail on HIGH/CRITICAL.
- **Deploy graceful-skip:** All deploy jobs check for secrets existence before attempting deployment; missing secrets = warning + exit 0.
- **Channel Health Aggregator:** Uses MongoDB aggregation pipelines with $lookup to join metrics with connector provider info. Percentile calculation uses linear interpolation on sorted arrays.

## Test Credentials
| User | Email | Password | Role |
|:---|:---|:---|:---|
| Demo Admin | demo@hotel.com | demo123 | super_admin |
