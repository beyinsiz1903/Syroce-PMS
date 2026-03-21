# Syroce PMS — Product Requirements Document

## Original Problem Statement
Multi-phase go-live war plan to make a hospitality SaaS platform production-safe and enterprise-grade, following `GO_LIVE_EXECUTION_BLUEPRINT.md`.

## Core Requirements
- Atomic booking operations (create, check-in, check-out)
- Tenant data isolation at DB query level
- Guaranteed PMS → OTA delivery (outbox pattern)
- Performance indexing for critical query paths
- Deep health monitoring
- OTA import/export reliability

## Architecture
```
/app/backend/
  core/
    atomic_booking.py         # Transactional booking create
    atomic_checkin_checkout.py # Transactional check-in/out
    tenant_db.py              # Tenant-scoped DB proxy
    outbox_service.py         # OTA-002: Outbox enqueue helper
    outbox_worker.py          # OTA-002: Background worker
    outbox_dispatcher.py      # OTA-002: Provider routing
  routers/
    outbox_admin.py           # OTA-002: Requeue/replay/status endpoints
  modules/
    reservations/             # Booking CRUD
    inventory/                # Room blocks
    pms_core/                 # State machine, front desk
  channel_manager/            # Exely, HotelRunner adapters
  health_check.py             # /health/deep with outbox stats
  startup.py                  # Indexes + worker startup
```

## Key Collections
- **bookings**: tenant_id, id, status, check_in, check_out
- **rooms**: tenant_id, status, housekeeping_status
- **folios**: tenant_id, booking_id, status
- **outbox_events**: id, tenant_id, event_type, status, payload, attempt_count, max_attempts, available_at, idempotency_key

## Completed Features

### Phase 1: Analysis (Complete)
- Codebase audit and go-live blueprint

### Phase 2: P0 Atomic Booking (BOOK-001) (Complete)
- Transactional booking create with rollback safety

### Day 2: Operational Integrity (Complete)
- **BOOK-002**: Atomic check-in/check-out with MongoDB transactions
- **PERF-001**: Compound indexes for bookings, rooms, folios, payments
- **OBS-001**: Deep health check endpoint (/health/deep)

### Day 3: Tenant Isolation PoC (Complete)
- **TI-001/TI-002**: TenantScopedDB proxy created and proven
- Not yet integrated into app service layer (P0 remaining)

### Day 4-5: OTA-002 Outbox Pattern (Complete - 2026-03-21)
- Replaced fire-and-forget `cm_push_event` with guaranteed delivery outbox
- Created `core/outbox_service.py` with enqueue helper, idempotency, retry policy
- Created `core/outbox_worker.py` with atomic claim, exponential backoff, stuck recovery
- Created `core/outbox_dispatcher.py` for EventSyncService routing
- Created `routers/outbox_admin.py` with status/events/requeue/replay endpoints
- Patched 4 business flows: booking create, booking cancel, room block create, room block release
- Enhanced `/health/deep` with detailed outbox stats
- 5 MongoDB indexes for efficient worker claiming
- 17 pytest tests — all passing

## Remaining P0
- Integrate TenantScopedDB proxy across application (tenant isolation)
- DATA-001: OTA → PMS automatic booking import reliability
- ARI-001: PMS → OTA guaranteed delivery via outbox (partially done by OTA-002)

## P1 Backlog
- Fix pre-existing test failures in test_hardening_comprehensive.py
- Fix lint errors in frontdesk_router.py, misc_router.py
- Data model repair (reduce collection sprawl)
- Observability & incident response
- Stress testing

## Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |
