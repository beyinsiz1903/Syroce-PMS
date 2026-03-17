# Syroce PMS — Product Requirements Document

## Original Problem Statement
Full-stack PMS + Channel Manager platform. The user's primary focus is **production-grade hardening** of the core reservation lifecycle, mapping, provider sync, and reconciliation systems before any new features.

## Core Architecture
- **Backend**: FastAPI + MongoDB
- **Frontend**: React + Shadcn/UI + Tailwind
- **Providers**: Exely (SOAP), HotelRunner (REST)

## Completed Work

### P0 — Folio Bug Fix (DONE)
- `GET /api/folio/booking/{booking_id}` endpoint
- Frontend ReservationDetailSidebar fixed

### P1 — Core Lockdown Block A: Domain Truth (DONE)
- Canonical state model (ReservationState, MutationType)
- Hardened ingest pipeline (idempotency, out-of-order, state transitions)
- Mapping validator (hard fail on unmapped/inactive/deleted)
- Provider capability matrix (Exely, HotelRunner)
- Reconciliation truth table (8 drift types)
- Observability endpoints (status, metrics, tracing, mapping health)
- Regression test suite: 48 unit tests

### P2 — Stress Tests & Lockdown Dashboard (DONE — 17 Mar 2026)
- **Replay Tests** (24 tests): Same events → same final state, same lineage, zero side effects
- **Duplicate Storm Tests** (14 tests): 5x-20x identical events → 1 CREATE + rest SKIP, stale events rejected, cancel always wins
- **ARI Stress Tests** (43 tests): Mass inventory, rate burst, restriction precedence, delta compilation, coalescing, error handling, retry
- **Lockdown Dashboard** (Frontend): Production readiness panel at `/lockdown` with:
  - System health overview (Ingest, Mapping, Reconciliation)
  - Key metrics (event count, duplicate rate, stale rate, success rate)
  - Ingest pipeline detail (24h window)
  - Rezervasyon lineage breakdown
  - Mapping health per provider with completeness bars
  - Reconciliation case stats
  - Provider capability matrix table
  - Reconciliation truth table
- **Total: 129 passing tests** (48 P1 + 81 P2)

## Remaining Tasks

### P2 (In Progress)
- [ ] Delta-only push + debounce correctness tests
- [ ] Operator incident panel (UI for managing reconciliation cases)

### P3 — Stress Testing (Upcoming)
- [ ] ARI stress tests with real provider simulation (429, timeout, delayed ACK)
- [ ] Replay tests with DB-level verification
- [ ] Duplicate storm tests with concurrency

### P3 — Financial Hardening
- [ ] Folio and Night Audit module hardening
- [ ] Per-tenant rollout gates and feature flags

### Refactoring
- [ ] Remove deprecated files (hotelrunner.py, client.py, exely_client_legacy.py)
- [ ] Archive old unused collections

## Key Files
- `/app/backend/domains/channel_manager/lockdown_router.py` — Lockdown API
- `/app/backend/domains/channel_manager/ingest/decision_engine.py` — Decision logic
- `/app/backend/domains/channel_manager/ingest/pipeline.py` — Ingest pipeline
- `/app/backend/domains/channel_manager/data_model.py` — Canonical models
- `/app/backend/domains/channel_manager/provider_capability.py` — Provider matrix
- `/app/backend/domains/channel_manager/ari/` — ARI pipeline
- `/app/backend/tests/test_core_lockdown.py` — P1 regression (48 tests)
- `/app/backend/tests/test_p2_replay.py` — P2 replay tests (24 tests)
- `/app/backend/tests/test_p2_duplicate_storm.py` — P2 duplicate storm (14 tests)
- `/app/backend/tests/test_p2_ari_stress.py` — P2 ARI stress (43 tests)
- `/app/frontend/src/pages/LockdownDashboard.jsx` — Lockdown Dashboard UI

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
