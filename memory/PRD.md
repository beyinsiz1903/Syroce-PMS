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
- Production-grade CI/CD with rollback, smoke tests, notifications
- Quarantine Burn-Down Dashboard (tech debt tracking)
- Weekly Proof Dashboard (week-over-week improvement tracking)
- **Deploy Dashboard — CI/CD → Control Plane integration (deploy event recording + visibility)**

## What's Been Completed

### Production Deployment Pipeline (2026-03-23)
- **CI/CD (`ci-cd.yml`):** Full deployment chain with Docker build/push to GHCR, rollout status wait, post-deploy smoke tests, automatic rollback on failure, Slack notifications
- **Manual Deploy (`deploy.yml`):** Build/push with cache, DB backup pre-deploy, rollback on failure, smoke tests, notifications, skip-backup option
- **Frontend K8s Manifest:** `infra/k8s/frontend-deployment.yml` — Deployment, Service, HPA with rolling update strategy, health probes

### Quarantine Burn-Down Dashboard (2026-03-23)
- **Backend:** `/api/ops/dashboard/tech-debt` endpoint reading quarantine manifest
  - 5 categories: stale_fixtures (P1), changed_api (P2), changed_impl (P3), external_dep (P4), meta-test (P5)
  - Per-category: count, effort hours, weekly target, weeks to clear
  - Overall: health score (30/100), health grade (D), estimated 3 weeks to zero
- **Frontend:** `TechDebtDashboard.jsx` — New "Teknik Borc" tab in Control Plane
  - Summary cards (total, weekly target, weeks remaining, health grade)
  - Progress bar with gradient
  - Expandable category cards with priority badges, test lists
- **Testing:** 26/26 backend + 13/13 frontend tests passed

### Weekly Proof Dashboard (2026-03-23)
- **Backend:** `/api/ops/dashboard/channel-health/weekly-proof` endpoint
  - Week-over-week aggregation: sync success, drift count, MTTR, SLA compliance, push p95
  - Improvement deltas (first week vs last week)
  - Configurable weeks parameter (2-52)
- **Frontend:** `WeeklyProofDashboard.jsx` — New "Deger Kaniti" tab in Control Plane
  - 5 improvement cards with delta/trend indicators
  - Sync & SLA trend line chart (Recharts)
  - Drift & MTTR bar chart
  - Push Latency p95 weekly bar chart
  - Weeks selector (4h, 8h, 12h)

### Channel Health Management Dashboard v2 (2026-03-23)
- **Upgraded from pilot screen to management screen**
- **Historical Trends API:** `/api/ops/dashboard/channel-health/trends`
- **Field KPIs API:** `/api/ops/dashboard/channel-health/field-kpis`
- **Frontend:** Recharts trend charts, 5 field KPI cards, period selector

### Environment Variable Unification (2026-03-23)
- Replaced all `REACT_APP_BACKEND_URL` → `VITE_BACKEND_URL` (123 files)

### Documentation & Quality Hardening (2026-03)
- README drift fixed, Security snapshot, Test health section
- Channel Capability Matrix, Pilot KPI Framework
- deploy.yml fixed (graceful-skip pattern)

### Quarantine Test Restoration (2026-03-23)
- 7 quarantined test files restored, 10 individually skipped tests fixed
- Test count: 391+ CI tests, 0 failures

## P0 — Completed
- [x] Frontend production build (Vite 8/Rolldown compatibility)
- [x] Flaky backend test stabilization
- [x] CI/CD pipeline reliability
- [x] Quarantine test restoration
- [x] CI/CD deployment jobs (graceful-skip pattern)
- [x] Documentation drift resolution
- [x] Channel Health Dashboard v1 (KPI strip + detail)
- [x] Channel Health Management Dashboard v2 (historical trends + field KPIs)
- [x] Environment variable unification
- [x] Production deployment pipeline (rollback + smoke test + notification)
- [x] Quarantine burn-down dashboard (tech debt tracking)
- [x] Weekly proof dashboard (week-over-week improvement)
- [x] CI/CD → Control Plane integration (deploy event dashboard)
- [x] CI/CD structured smoke test output (table with endpoint/status/latency/result)
- [x] CI/CD enhanced notifications (GitHub annotations + GITHUB_STEP_SUMMARY + Slack)
- [x] CHANGELOG truth cleanup (stale REACT_APP_BACKEND_URL reference fixed)

## P1 — Upcoming
- [ ] Fix remaining quarantined tests: stale_fixtures (rate_manager, 10 tests)
- [ ] Fix remaining quarantined tests: changed_api (10 tests)
- [ ] Fix remaining quarantined tests: changed_implementation (13 tests)
- [ ] Channel manager inventory ledger alignment with room-type system
- [ ] Exely/HotelRunner sandbox testing (per capability matrix gaps)

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
- **Vite 8 `.jsx` Convention:** All React component files use `.jsx` extension
- **Test Isolation:** Battle tests use `random.randint(2100, 9999)` for date ranges
- **Quarantine Fix Pattern:** Far-future dates (3000-6000 day offsets), sync pymongo for DB verification
- **yarn audit CI Gate:** Uses bitmask check `(exit_code & 24) != 0` for HIGH/CRITICAL only
- **Deploy graceful-skip:** All deploy jobs check for secrets existence before deployment
- **Deployment Rollback:** `kubectl rollout undo` on failure with rollout status wait
- **Tech Debt Tracking:** Direct import from quarantine_manifest.py, no DB dependency
- **Weekly Proof:** MongoDB aggregation with week-based date windowing
- **Deploy Event Bridge:** CI/CD workflows POST deploy results to backend; Control Plane renders deploy history with smoke test details, rollback events, and per-environment success rates

## Key API Endpoints
- `GET /api/ops/dashboard/channel-health` — Current period health metrics
- `GET /api/ops/dashboard/channel-health/trends` — Historical time-series data
- `GET /api/ops/dashboard/channel-health/field-kpis` — Operational field KPIs
- `GET /api/ops/dashboard/channel-health/weekly-proof` — Week-over-week improvement
- `GET /api/ops/dashboard/tech-debt` — Quarantine burn-down tracking
- `POST /api/ops/deploys` — Record deploy event (CI/CD → Control Plane)
- `GET /api/ops/dashboard/deploys` — Deploy history (newest first, env filter, limit)
- `GET /api/ops/dashboard/deploy-stats` — Deploy statistics per environment

## Test Credentials
| User | Email | Password | Role |
|:---|:---|:---|:---|
| Demo Admin | demo@hotel.com | demo123 | super_admin |
