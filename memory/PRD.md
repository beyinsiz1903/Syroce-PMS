# Syroce PMS — Product Requirements Document

## Original Problem Statement
Address significant technical debt in the Syroce Hotel PMS system. The primary focus is the staged decomposition of the monolithic `routers/pms.py` file to improve maintainability and reduce complexity, alongside hardening CI/CD, tenant isolation, and observability.

## User Personas
- **Hotel Staff**: Front desk, housekeeping, management
- **System Administrators**: DevOps, platform engineers
- **Developers**: Maintaining and extending the PMS codebase

## Core Requirements
1. **P0 (DONE)**: Staged decomposition of `pms.py` monolith
2. **P0 (DONE)**: Load + chaos testing to prove reliability under stress
3. **P0 (DONE)**: Go-Live Hardening (Vite prod build, Nginx, Runbook, SLO/SLA, Incident Playbook)
4. **P1**: Frontend decomposition (`App.jsx`)
5. **P1**: `room-move-history` bug fix
6. **P2**: CI/CD hardening (Ruff UP rules, stricter linting)
7. **P2**: Import boundary exceptions cleanup

## Architecture
```
/app/backend/routers/
├── pms.py                  # 21 lines — backward-compat import only
├── pms_availability.py     # 267 lines — Room blocks + availability (CRITICAL)
├── pms_reservations.py     # 579 lines — Reservation details, search, mutations
├── pms_room_details.py     # 213 lines — Room notes, minibar, enhanced details
├── pms_room_queue.py       # 212 lines — Early arrival queue management
├── pms_services.py         # 283 lines — Staff tasks, allotments, groups, setup
├── pms_bookings.py         # 568 lines — Booking CRUD (Stage 2)
├── pms_dashboard.py        # 276 lines — Dashboard endpoints (Stage 2)
├── pms_rooms.py            # 611 lines — Room CRUD (pre-existing)
├── pms_guests.py           # 164 lines — Guest CRUD (pre-existing)
└── pms_shared.py           # 21 lines — Pure helper functions
```

## What's Been Implemented

### Stage 1 (Pre-existing)
- Room and guest modules extracted
- CI/CD pipeline with sandbox regression gate
- Tenant isolation middleware
- Wire failure tracking

### Stage 2 (Previous Session)
- Extracted `pms_bookings.py` (10 booking routes)
- Extracted `pms_dashboard.py` (3 dashboard routes)
- Created `pms_shared.py` for pure helpers
- Reduced pms.py from 2934 to 1384 lines

### Stage 3 (Completed)
- Load + Chaos Testing Framework (18 tests)
- Bug Fixes (ObjectId serialization x2)
- Full decomposition: pms_services, pms_room_queue, pms_room_details, pms_reservations, pms_availability
- pms.py reduced from 1384 to 21 lines
- 116/116 tests pass

### Go-Live Hardening (Current Session — COMPLETE)
- **Vite Prod Build Optimization**: chunk splitting (vendor-react, vendor-charts, vendor-ui), sourcemap disabled, es2020 target, CSS minification, build output 6.9MB
- **Nginx Container Hardening**: gzip level 6, security headers (Permissions-Policy, X-Frame-Options, X-Content-Type-Options), immutable cache for hashed assets, proxy buffering, dot-file blocking
- **Go-Live Runbook** (`/app/docs/procedures/GO_LIVE_RUNBOOK.md`): Pre-deploy checklist, DB backup, deploy process, post-deploy smoke test, rollback matrix, communication protocol
- **SLO/SLA Definitions** (`/app/docs/SLO_SLA.md`): 3-tier SLO model (Critical 99.9%, Operational 99.5%, Auxiliary 99.0%), error budget policy, customer SLA tiers, response time targets
- **Incident Playbook** (`/app/docs/procedures/INCIDENT_PLAYBOOK.md`): SEV-1 to SEV-4 classification, response procedures, common scenario runbooks, post-mortem template, escalation matrix
- **CI Fix**: Restored `create_test_user.py` to `backend/` root (was missing from `_legacy/` move)
- **Lint Cleanup**: Fixed 4 unused imports in pms_bookings, pms_dashboard, pms_room_queue

## Test Coverage
- `/app/backend/tests/test_pms_route_wiring.py` — 59 route reachability tests
- `/app/backend/tests/test_pms_decomposition_stage3.py` — 39 functional regression tests
- `/app/backend/load_tests/` — 18 load/chaos tests
- `/app/test_reports/iteration_155.json` — Full test report

## Prioritized Backlog

### P0 (Next)
- None — All P0 items complete

### P1
- Frontend refactoring: Decompose monolithic `App.jsx` (2132 lines)
- Fix pre-existing `room-move-history` endpoint bug (optional params handling)
- Load test expansion

### P2
- CI/CD hardening: Apply `pyupgrade` (UP) Ruff rules
- Resolve 3 known exceptions in `check_import_boundaries.py`
- Architectural debt cleanup

### P3
- `pms_shared.py` governance: Monitor for scope creep
- Performance optimization for availability queries under high concurrency

## Constraints
- `pms_shared.py`: ONLY pure helper functions. No business logic, no DB access, no state mutation.
- All routes must be prefixed with `/api`
- Room blocks and availability endpoints require `Idempotency-Key` header for POST operations
- MongoDB `_id` must never leak into API responses

## Credentials
- Test user: `demo@hotel.com` / `demo123`
