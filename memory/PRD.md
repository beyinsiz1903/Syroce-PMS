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

### P0 — Sprint 4 (Room-Type Strategy)
- RFC/ADR for Phase C "Room-Type Level Strategy"
- Design room-type strategy from audit trail telemetry
- Align channel manager inventory ledger with hardened booking system
- PMS battle tests: split reservation, no-show, room change

### P1 — Governance Phase 3 (Support Tooling)
- Support Dashboard: tenant health, quick actions
- Impersonate tenant, audit log viewer, ticket system

### P1 — Governance Phase 4 (Pilot KPI Dashboard)
- Adoption rate tracking, feature usage heatmap, error rate timeline, response percentiles

### P1 — Hardening (Blueprint Week 2)
- Key rotation (data model + API + ReEncryptionWorker)
- PMS battle tests (split reservation, no-show, room change)

### P1 — Stress & Exposure (Blueprint Week 3)
- Reservation Burst test (15K reservations)
- ARI Storm test (120K updates)
- Provider Downtime simulation
- Pilot hotel shadow mode + canary rollout

### P2 — Tech Debt
- ~403 failing tests → quarantine triage (ADR-002 strategy ready)
- ~264 legacy DB imports to tenant-scoped access
- README and CI workflow file cleanup
- Crypto Migration (SEC-002) & Secrets Management (SEC-001)
- Strict Tenant Mode enablement

### P2 — Enhancements
- Ctrl+K shortcut for quick Trace lookup
- Login endpoint to return full module list
