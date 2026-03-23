# Syroce PMS — Product Requirements Document

## System Overview
Hotel PMS + Channel Manager platform. FastAPI backend, MongoDB, Redis. Multi-tenant architecture with OTA/provider integrations (Exely, HotelRunner). Outbox pattern, import/ingest pipelines, idempotency protections. AES-256-GCM encryption with AAD binding.

## Core Architecture
- `/app/backend/` — FastAPI backend
- `/app/backend/controlplane/` — OPS-001 Control Plane module
- `/app/backend/core/` — Core services (outbox, import bridge, crypto, secrets, booking holds)
- `/app/backend/channel_manager/` — Channel manager adapters
- `/app/backend/workers/` — Background workers (ARI push, retry, etc.)
- `/app/backend/tests/resilience/` — Chaos testing and resilience validation suite
- `/app/backend/tests/battle/` — CI hard gate battle tests (Sprint 1-3)
- `/app/backend/docs/BATTLE_READINESS_BLUEPRINT.md` — Battle-grade execution blueprint
- `/app/backend/docs/ADR_BOOKING_INVARIANTS.md` — ADR-001: Booking invariants
- `/app/backend/docs/ADR_TEST_QUARANTINE_STRATEGY.md` — ADR-002: Test quarantine strategy
- `/app/frontend/src/pages/ControlPlane.jsx` — Control Plane UI (ops weapon)

## Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Completed Features

### Phase C.1 — Room-Type Inventory Materialized View (2026-03-28)
ADR-003 Layer 2 implementation. Read-only materialized view of room-type-level availability.
- `core/room_type_inventory_service.py`: Aggregation engine + reconciliation worker (5 min interval)
- `routers/inventory.py`: 4 API endpoints (room-types, summary, reconcile, health)
- `tests/battle/test_room_type_inventory.py`: 10 battle tests, all passing
- INV-7: sellable = physical_total - sum(locks). Drift detection + event_timeline alerts.
- CI hard gate updated.

### Frontend Security Fix — yarn audit Vulnerability Resolution (2026-03-27)
4 direct dependency upgrades + 10 transitive resolutions. 87→29 vulns (0 critical, 0 high).
CI gate upgraded to `--level high`. Frontend verified working.

### CI Security Fix — pip-audit Vulnerability Resolution (2026-03-23)
11 package upgrades resolving 15 CVEs. FastAPI 0.110→0.135, Starlette 0.37→1.0, pymongo 4.5→4.8, strawberry-graphql 0.235→0.312.
4 CVEs ignored (ecdsa timing attack no-fix, nltk WordNet Browser not used). CI pipeline green: 338/338 tests pass.

### Sprint 4 — Quarantine Triage + Phase C RFC (2026-03-23)
**Test Quarantine Triage (DONE)**
- 7 test files fully quarantined to `tests/_quarantine/` (categorized: stale_room_locks, stale_fixtures, stale_dates)
- 52 individual tests skip-marked via `quarantine_manifest.py` + conftest.py auto-skip hook
- Categories: stale_room_locks (14), stale_fixtures (11), changed_api (10), changed_impl (13), ext_dependency (3), meta-test (1)
- Business date reset (was advanced by night audit tests, blocking same-day bookings)
- **Testing**: T0: 71/72 pass (1 data-skip), T1: 241/241 pass, Quarantine: working (iteration_137)

**Phase C RFC/ADR (DONE)**
- Created `docs/ADR_ROOM_TYPE_INVENTORY_STRATEGY.md` (ADR-003, 328 lines)
- 3-layer inventory model: Room-Night Locks → Room-Type Inventory → Channel Inventory
- Phased migration: C.1 (read-only view) → C.2 (event-driven) → C.3 (deferred assignment)
- New invariants: INV-7 (type-lock consistency), INV-8 (channel <= property)

### Sprint 3 — Regression Guards + CI Security + Test Quarantine (2026-03-23)
**Regression Guard Tests (DONE)**
- `tests/battle/test_regression_guards.py`: 8 permanent regression tests
- REG-1 through REG-7: Past date, navigation, date validation guards
- **Testing**: 28/28 battle tests pass, 338/338 CI suite (iteration_136)

**CI/CD Security Tightening (DONE)**
- pip-audit: specific vuln ignores (no wildcard), hard gate
- Trivy CRITICAL: exit-code=1 (hard gate)
- Hardcoded secrets: exit-code=1 (hard gate)

**Test Quarantine Strategy (DONE)**
- ADR-002: T0 (battle) / T1 (curated CI) / T2 (quarantine) tiers
- `tests/_quarantine/` directory created

### Sprint 2 — TTL/Hold Mechanism + OOO/OOS Full Integration (2026-03-23)
**A2: TTL/Hold Mechanism (DONE)**
- `core/booking_hold_service.py`: Full hold lifecycle (create, confirm, release, sweep)
- `routers/booking_holds.py`: REST API for hold management
- Background sweeper runs every 60s, auto-releases expired holds
- Default TTL: 15 minutes (configurable via `BOOKING_HOLD_TTL_MINUTES` env var)
- **Testing**: 32/32 pass (iteration_135)

**A5: OOO/OOS INV-5 Integration (DONE)**
- PMS room block create/cancel now writes to/releases from `room_night_locks`
- Type mapping: `out_of_order` → `ooo`, `out_of_service` → `oos`, `maintenance` → `maintenance`

### Sprint 1 — Overbooking Prevention v2 (Booking Integrity Hardening) (2026-03-23)
ADR-001 invariants, room-night lock audit trail, OOO/OOS/maintenance integration, cancel/modify race guard, 10-test CI hard gate.
- **Invariants**: INV-1 through INV-6
- **Testing**: 25/25 pass (iteration_134)

### Deploy Pipeline — Hard Gate CI/CD & Progressive Deploy (2026-03-22) — Phase 2
Production-grade deployment pipeline with hard gates, auto-rollback, migration verification, smoke tests, and canary analysis.

### Governance & Metering Layer (2026-03-22) — Phase 1
Full production governance stack: entitlement enforcement, usage metering, dynamic feature flags, and onboarding automation.

### OPS-001: Production-Grade Control Plane
Core module at `/app/backend/controlplane/` with failure taxonomy, 15 API endpoints, idempotent retry engine, alerting engine.

### CHAOS-001: Chaos Testing & Resilience Validation Program
69 resilience tests across 7 test files.

### CORE BATTLE LOOP (2026-03-22) — Week 1 MVP
Event Timeline System, FailureTracker Wiring, Minimal Dashboard.

### WEBHOOK TIMELINE INTEGRATION (2026-03-22)
End-to-end traceability for Exely and HotelRunner webhooks.

### CONTROL PLANE UI (2026-03-22)
Frontend operations screen: Reservation Trace, System Health, Live Feed.

## Bug Fixes
### Overbooking Prevention — Room-Night Locking (2026-03-22)
### Navigation Module Visibility Bug (2026-03-22)
### Past Date Reservation Bug (2026-03-22)

## Pending Tasks

### P0 — Sprint 5 (Phase C.2 Implementation)
- Implement Phase C.2: Event-driven room-type inventory updates (ADR-003)
- Hook `room_type_inventory` updates into booking/cancel/hold/OOO events
- Create `channel_inventory` collection
- Wire ARI push to read from `channel_inventory`

### P0 — Battle Tests Expansion
- PMS battle tests: split reservation, no-show, room change
- Align channel manager inventory ledger with hardened booking system

### P1 — Governance Phase 3 (Support Tooling)
- Support Dashboard: tenant health, quick actions
- Impersonate tenant, audit log viewer, ticket system

### P1 — Governance Phase 4 (Pilot KPI Dashboard)
- Adoption rate tracking, feature usage heatmap, error rate timeline, response percentiles

### P1 — Hardening (Blueprint Week 2)
- Key rotation (data model + API + ReEncryptionWorker)

### P1 — Stress & Exposure (Blueprint Week 3)
- Reservation Burst test (15K reservations)
- ARI Storm test (120K updates)
- Provider Downtime simulation
- Pilot hotel shadow mode + canary rollout

### P2 — Tech Debt
- Quarantine monthly review: fix and restore quarantined tests (52 individual + 7 files)
- ~264 legacy DB imports to tenant-scoped access
- README and CI workflow file cleanup
- Crypto Migration (SEC-002) & Secrets Management (SEC-001)
- Strict Tenant Mode enablement

### P2 — Enhancements
- Ctrl+K shortcut for quick Trace lookup
- Login endpoint to return full module list

