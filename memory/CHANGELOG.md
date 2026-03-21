# Syroce PMS — Changelog

## 2026-03-21: Day 2-3 Implementation (BOOK-002, TI-001, PERF-001, OBS-001)

### BOOK-002: Atomic Check-in/Check-out (P0)
- Created `core/atomic_checkin_checkout.py` with `check_in_booking_atomic()` and `check_out_booking_atomic()`
- Uses MongoDB transactions (snapshot read, majority write) for full atomicity
- Check-in: booking→checked_in, room→occupied, folio created, audit log, outbox event
- Check-out: booking→checked_out, room→dirty, folio→closed, housekeeping task, audit log, outbox event
- Refactored 8+ code paths: FrontDeskService, early_checkin, group check-in/out, walk-in, mobile quick check-in, generic update service
- Created `tests/test_atomic_checkin_checkout.py` (7 tests)

### TI-001: Tenant Isolation Enforcement (P0)
- Created `core/tenant_db.py` with `TenantScopedDB` and `TenantScopedCollection` classes
- Auto-injects `tenant_id` into all queries on tenant-scoped collections
- Blocks cross-tenant queries/inserts/updates/deletes with `TenantViolationError`
- 50+ tenant-scoped collections defined
- Created `tests/test_tenant_isolation_proof.py` (11 tests)

### PERF-001: Compound Indexes for Hot Queries
- Added 14 compound indexes in `startup.py → _ensure_performance_indexes()`
- Covers bookings (status+dates, room+dates, guest+status), rooms (type, status), folios, guests, outbox, housekeeping, audit trail

### OBS-001: Deep Health Check Endpoint
- Added `GET /health/deep` endpoint in `health_check.py`
- Returns: mongo (replica set status), redis, outbox (pending/failed), night audit

### Testing
- Testing agent validation: 31 passed, 1 skipped, 0 failed (iteration_116)
- Manual tests: check-in/out lifecycle, error cases, concurrent safety

---

## 2026-03-21: Day 1 Implementation (BOOK-001)

### BOOK-001: Atomic Booking / Overbooking Prevention (P0)
- Created `core/atomic_booking.py` with `create_booking_atomic()`
- MongoDB replica set enabled for transaction support
- 15+ booking creation paths consolidated
- Compound index for conflict detection
- Tested: 10 concurrent requests → 1 success, 9 conflicts (HTTP 409)
- Created `GO_LIVE_EXECUTION_BLUEPRINT.md`

---

## Prior Work (Previous Sessions)
- Full PMS feature set: bookings, rooms, guests, folios, housekeeping
- Channel manager: Exely, HotelRunner integrations
- Night audit automation
- Guest journey & online check-in
- Rate management
- Reporting system
- Rate Manager Bulk Update ~6.5x Faster
