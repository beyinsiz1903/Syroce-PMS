# Syroce PMS — Product Requirements Document

## System Overview
Hotel PMS + Channel Manager platform. FastAPI backend, MongoDB, Redis. Multi-tenant architecture with OTA/provider integrations (Exely, HotelRunner). Outbox pattern, import/ingest pipelines, idempotency protections. AES-256-GCM encryption with AAD binding.

## Core Architecture
- `/app/backend/` — FastAPI backend
- `/app/frontend/` — React frontend (Vite 8.0.1 build system)
- `/app/backend/controlplane/` — OPS-001 Control Plane module
- `/app/backend/core/` — Core services (outbox, import bridge, crypto, secrets, booking holds, room-type inventory)
- `/app/backend/channel_manager/` — Channel manager adapters
- `/app/backend/workers/` — Background workers (ARI push, retry, etc.)
- `/app/backend/tests/resilience/` — Chaos testing and resilience validation suite
- `/app/backend/tests/battle/` — CI hard gate battle tests (Sprint 1-4, Phase C.1)
- `/app/backend/docs/BATTLE_READINESS_BLUEPRINT.md` — Battle-grade execution blueprint
- `/app/backend/docs/ADR_BOOKING_INVARIANTS.md` — ADR-001: Booking invariants
- `/app/backend/docs/ADR_TEST_QUARANTINE_STRATEGY.md` — ADR-002: Test quarantine strategy
- `/app/backend/docs/ADR_ROOM_TYPE_INVENTORY_STRATEGY.md` — ADR-003: Room-type inventory (3-layer model)
- `/app/backend/docs/SECURITY_ACCEPTED_RISKS.md` — Frontend vulnerability status (0 remaining)
- `/app/frontend/vite.config.js` — Vite 8 config with OXC JSX, @/ alias, proxy
- `/app/frontend/src/pages/ControlPlane.jsx` — Control Plane UI (ops weapon)

## Frontend Build System
- **Build tool:** Vite 8.0.1 + @vitejs/plugin-react 6.0.1
- **Bundler:** Rolldown (Rust-based, replaces webpack)
- **Transformer:** OXC (Rust-based, replaces esbuild/babel)
- **Config:** `oxc.lang: 'jsx'` enables JSX parsing in .js files
- **Env vars:** `VITE_*` prefix (was `REACT_APP_*`)
- **Entry:** `/app/frontend/index.html` (root level, not public/)
- **Dependency overrides:** Both `resolutions` (yarn) and `overrides` (npm) for cross-package-manager CI compatibility

## Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Completed Features

### ESLint ajv CI/CD Fix + websocket.js Lint Fix (2026-03-23)
- npm `overrides` field added to `package.json` for CI compatibility (ajv v6.12.6 forced in both yarn and npm)
- `websocket.js` `connect()` method made async, `useWebSocket` hook updated for async compat
- ESLint: 0 errors, 0 warnings (fully clean)

### CRA → Vite Migration (2026-03-23)
Full build system migration from Create React App to Vite 8.0.1. Removed react-scripts, @craco/craco.
131 env var references migrated (REACT_APP_* → VITE_*). OXC JSX config for .js files.
**87 → 0 vulnerabilities** (100% resolved). Packages audited: 1542 → 600. Dev startup: ~150ms.

### Frontend Dependency Hardening — Bucket 1 (2026-03-28)
5 packages resolved via yarn resolutions: lodash, qs, postcss, diff, @eslint/plugin-kit.
29 → 14 vulnerabilities (52% reduction). ajv now resolved post-CRA removal.

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
Test quarantine triage, business date fix, ADR-003 Phase C RFC.

### Sprint 3 — Regression Guards + CI Security + Test Quarantine (2026-03-23)
8 permanent regression tests. CI/CD security tightening. Test quarantine strategy (ADR-002).

### Sprint 2 — TTL/Hold Mechanism + OOO/OOS Full Integration (2026-03-23)
Full hold lifecycle, background sweeper, REST API. OOO/OOS integration with room_night_locks.

### Sprint 1 — Overbooking Prevention v2 (2026-03-23)
ADR-001 invariants, room-night lock audit trail, cancel/modify race guard, 10-test CI hard gate.

### Earlier
Deploy Pipeline, Governance & Metering, Control Plane, Chaos Testing, Core Battle Loop, Webhook Timeline.

## Bug Fixes
### ESLint ajv CI/CD Crash (2026-03-23)
### Overbooking Prevention — Room-Night Locking (2026-03-22)
### Navigation Module Visibility Bug (2026-03-22)
### Past Date Reservation Bug (2026-03-22)

## Pending Tasks

### P0 — Flaky Backend Tests
- Fix intermittent 409 Conflict errors in `tests/battle/test_booking_integrity.py` (state pollution)
- Ensure proper test isolation with database cleanup fixtures
- Critical for reliable CI/CD pipeline

### P0 — Sprint 5 (Phase C.2 Implementation)
- Implement Phase C.2: Event-driven room-type inventory updates (ADR-003)
- Hook `room_type_inventory` updates into booking/cancel/hold/OOO events
- Create `channel_inventory` collection
- Wire ARI push to read from `channel_inventory`

### P0 — Battle Tests Expansion
- PMS battle tests: split reservation, no-show, room change
- Align channel manager inventory ledger with hardened booking system

### DONE — Frontend Dependency Hardening (ALL RESOLVED)
- [x] yarn resolutions for Bucket 1: lodash, qs, postcss, diff, @eslint/plugin-kit (29→14 vulns)
- [x] CRA → Vite 8 migration (14→2 vulns, removed react-scripts + @craco/craco)
- [x] ajv resolution (2→0 vulns, now works without CRA blocking)
- [x] npm `overrides` field added for CI compatibility (yarn resolutions + npm overrides)
- [x] websocket.js ESLint parsing error fixed (async connect)
- **Result: 87 → 0 vulnerabilities, 0 critical, 0 high, 0 moderate, 0 low**
- **ESLint: 0 errors, 0 warnings (fully clean)**

### P1 — Quarantined Tests
- Fix tests in `tests/_quarantine/` starting with stale_dates category
- Fix flaky `test_confirm_hold_api` (state pollution in full suite)

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
