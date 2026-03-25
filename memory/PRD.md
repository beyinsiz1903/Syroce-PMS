# Syroce PMS — Product Requirements Document

## Original Problem Statement
Address significant technical debt in the Syroce Hotel PMS system. The primary focus is the staged decomposition of the monolithic `routers/pms.py` file to improve maintainability and reduce complexity, alongside hardening CI/CD, tenant isolation, and observability.

## User Personas
- **Hotel Staff**: Front desk, housekeeping, management
- **System Administrators**: DevOps, platform engineers
- **Developers**: Maintaining and extending the PMS codebase

## Core Requirements
1. **P0**: Staged decomposition of `pms.py` monolith
2. **P1**: Load + chaos testing to prove reliability under stress
3. **P1**: Frontend decomposition (`App.jsx`)
4. **P2**: CI/CD hardening (Ruff UP rules, stricter linting)
5. **P2**: Load + chaos testing expansion

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

### Stage 3 (Current Session — COMPLETE)
- **Load + Chaos Testing Framework** (18 tests):
  - Availability invariant tests (concurrent reads, booking impact)
  - Booking integrity tests (double-booking prevention, count accuracy)
  - Concurrent mutation tests (room blocks, staff tasks, dashboard load)
- **Bug Fixes**:
  - ObjectId serialization in `/api/pms/allotment-contracts` (POST)
  - ObjectId serialization in `/api/pms/group-reservations` (POST)
- **Sub-stage 3a**: Extracted `pms_services.py` (11 routes: room-services, staff-tasks, allotments, groups, setup)
- **Sub-stage 3b**: Extracted `pms_room_queue.py` (5 queue routes)
- **Sub-stage 3c**: Extracted `pms_room_details.py` (3 room detail routes + models)
- **Sub-stage 3d**: Extracted `pms_reservations.py` (8 reservation routes + models)
- **Sub-stage 3d-final**: Extracted `pms_availability.py` (5 routes: blocks + availability)
- **pms.py reduced from 1384 to 21 lines** (backward-compat import only)
- **Total: 116/116 tests pass** (59 route wiring + 39 functional + 18 load)

## Test Coverage
- `/app/backend/tests/test_pms_route_wiring.py` — 59 route reachability tests
- `/app/backend/tests/test_pms_decomposition_stage3.py` — 39 functional regression tests
- `/app/backend/load_tests/` — 18 load/chaos tests
- `/app/test_reports/iteration_155.json` — Full test report

## Prioritized Backlog

### P0 (Next)
- None — Stage 3 decomposition is complete

### P1
- Frontend refactoring: Decompose monolithic `App.jsx`
- CI/CD hardening: Apply `pyupgrade` (UP) Ruff rules
- Fix pre-existing `room-move-history` endpoint bug (optional params handling)

### P2
- Load + chaos testing expansion (Locust-based sustained load)
- Resolve 3 known exceptions in `check_import_boundaries.py`
- Architectural debt cleanup

### P3
- `pms_shared.py` governance: Monitor for scope creep (pure helpers only)
- Performance optimization for availability queries under high concurrency

## Constraints
- `pms_shared.py`: ONLY pure helper functions. No business logic, no DB access, no state mutation.
- All routes must be prefixed with `/api`
- Room blocks and availability endpoints require `Idempotency-Key` header for POST operations
- MongoDB `_id` must never leak into API responses

## Credentials
- Test user: `demo@hotel.com` / `demo123`
