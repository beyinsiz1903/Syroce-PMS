# Syroce PMS — Product Requirements Document

## Original Problem Statement
Multi-phase go-live war plan to make a hospitality SaaS platform production-safe and enterprise-grade, following `GO_LIVE_EXECUTION_BLUEPRINT.md`.

## Core Requirements
- Atomic booking operations (create, check-in, check-out)
- Tenant data isolation at DB query level
- Guaranteed PMS → OTA delivery (outbox pattern)
- Reliable OTA → PMS automatic booking import
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
    import_bridge_service.py  # DATA-001: Auto-import OTA → PMS
    import_decision.py        # DATA-001: Classification layer
    import_retry_worker.py    # DATA-001: Background retry worker
  routers/
    outbox_admin.py           # OTA-002: Requeue/replay/status
    import_admin.py           # DATA-001: Review queue/retry/approve
  modules/
    reservations/             # Booking CRUD
    inventory/                # Room blocks
    pms_core/                 # State machine, front desk
  channel_manager/            # Exely, HotelRunner adapters
    ingest/pipeline.py        # Modified: triggers import bridge on CREATE
  health_check.py             # /health/deep with outbox + import stats
  startup.py                  # Indexes + worker startup
```

## Key Collections
- **bookings**: tenant_id, id, status, check_in, check_out, source (provider linkage)
- **rooms**: tenant_id, status, housekeeping_status
- **folios**: tenant_id, booking_id, status
- **outbox_events**: id, tenant_id, event_type, status, payload, attempt_count, max_attempts
- **imported_reservations**: id, tenant_id, provider, connector_id, external_reservation_id, import_status, booking_id, retry_count

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
- Replaced fire-and-forget with guaranteed delivery outbox
- 17 pytest tests — all passing

### Day 6: DATA-001 OTA → PMS Import Bridge (Complete - 2026-03-21)
- Import state machine: pending_auto_import → processing → imported/review_required/retry/failed/duplicate
- Atomic claim pattern (find_one_and_update) prevents concurrent processing
- 3-layer duplicate prevention (unique index, booking source check, import status)
- Auto-import via create_booking_atomic (single booking creation path)
- Exponential backoff retry (30s → 2m → 10m → 30m → 2h)
- Review queue for mapping failures (unmapped room/rate, invalid dates, missing guest)
- Background import retry worker with stuck recovery
- Admin endpoints: /api/imports/status, review-queue, events, retry, approve-and-import, dismiss
- Enhanced /health/deep with import_bridge metrics
- Pipeline integration: ingest pipeline triggers import bridge on new reservation CREATE
- 22 pytest + 16 API tests — all passing (38 total)

## Remaining P0
- Integrate TenantScopedDB proxy across application (tenant isolation)
- ARI-001: PMS → OTA guaranteed delivery (partially done by OTA-002)

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
