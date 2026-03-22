# Syroce PMS — Changelog

## 2026-03-22: Core Battle Loop — Week 1 MVP

### Event Timeline System
- Created `controlplane/timeline_writer.py` — TimelineWriter with fire-and-forget `append()` 
- Created `controlplane/timeline_reader.py` — TimelineReader with entity/correlation/external_id lookup, search, gap detection
- Created `controlplane/timeline_router.py` — 5 API endpoints under `/api/ops/timeline/*`
- Added `event_timeline` collection with 5 indexes (entity, correlation, external_id, stage_health, TTL 90d)
- Registered timeline router in `bootstrap/router_registry.py`
- Added timeline indexes to `startup.py`

### FailureTracker Wiring
- Modified `core/import_bridge_service.py` — FailureTracker + Timeline at import_decided, stored, queued, failure stages
- Modified `core/outbox_worker.py` — FailureTracker + Timeline at dispatched, confirmed, failure stages
- Both use fire-and-forget pattern (failures are logged but never block main flow)

### Dashboard Aggregator
- Created `controlplane/dashboard_aggregator.py` — DashboardAggregator (8 parallel queries), health score algorithm, DashboardSnapshotWorker
- Created `controlplane/dashboard_router.py` — 5 API endpoints under `/api/ops/dashboard/*`
- Added `cp_health_snapshots` collection with 3 indexes (tenant, type, TTL 7d)
- Snapshot worker runs every 60s, started in `startup.py`

### Testing
- 21 API tests all passing (test_timeline_dashboard_api.py)
- Reservation trace: <1 second (goal was <5 seconds)
- Dashboard response: <500ms

---

## 2026-02-15: Battle-Readiness Blueprint
- Created 2576-line execution blueprint (`BATTLE_READINESS_BLUEPRINT.md`)
- 10-section production evolution plan with data models, APIs, workflows

## Earlier (pre-fork history)
- OPS-001: Control Plane (15 endpoints, failure taxonomy, retry engine, runbooks)
- CHAOS-001: Resilience testing (69 tests, 7 test files)
- Production infrastructure (crypto, secrets, tenant isolation, etc.)
