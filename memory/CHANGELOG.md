# Syroce PMS — Changelog

## 2026-03-21: OTA-002 Outbox Pattern Implementation (P0 — Guaranteed Delivery)

### Core: Outbox Service (`core/outbox_service.py`)
- `enqueue_outbox_event()` helper with transaction session support
- Idempotency key generation (tenant:event_type:entity:payload_hash)
- Error classification: retryable (timeout, 5xx, network) vs permanent (mapping, auth, schema)
- Exponential backoff: 0s → 30s → 2min → 10min → 30min
- 8 OTA event type constants (booking.created/cancelled/modified, inventory.blocked/released/updated, restriction.updated, rate.updated)

### Core: Outbox Worker (`core/outbox_worker.py`)
- Production async background worker with poll + claim loop
- Atomic claim pattern (find_one_and_update) prevents duplicate processing
- `max_attempts` field filter ensures legacy migration events are untouched
- Stuck processing recovery (events in "processing" > 120s reset to "retry")
- Worker metrics: processed/failed/retry counts, last processed timestamp

### Core: Outbox Dispatcher (`core/outbox_dispatcher.py`)
- Routes outbox events to EventSyncService for per-connector dispatch
- Maps OTA event types to channel manager operations
- Fallback dispatch via webhook when EventSyncService unavailable

### Admin Endpoints (`routers/outbox_admin.py`)
- `GET /api/outbox/status` — Queue health + worker metrics
- `GET /api/outbox/events?status=&provider=` — List events with filters
- `POST /api/outbox/{id}/requeue` — Requeue single failed event
- `POST /api/outbox/replay?provider=&tenant_id=` — Replay all failed events

### Business Flow Patches (4 flows)
- `create_reservation_service.py`: Removed `cm_push_event` fire-and-forget, replaced with `enqueue_outbox_event(BOOKING_CREATED)`
- `reservation_state_machine.py`: Added outbox event on booking cancellation (`BOOKING_CANCELLED`)
- `create_room_block_service.py`: Replaced legacy outbox insert with `enqueue_outbox_event(INVENTORY_BLOCKED)`
- `release_room_block_service.py`: Replaced legacy outbox insert with `enqueue_outbox_event(INVENTORY_RELEASED)`

### Health Check Enhanced
- `/health/deep` now includes: pending, processing, retry, failed, processed_24h, oldest_pending_seconds, last_processed_at, provider_failures

### Indexes (5 new)
- `idx_outbox_worker_claim`: (tenant_id, status, available_at, created_at)
- `idx_outbox_provider_status`: (tenant_id, provider, status, created_at)
- `idx_outbox_idempotency`: (idempotency_key) unique partial
- `idx_outbox_correlation`: (correlation_id)
- `idx_outbox_entity_event`: (entity_type, entity_id, event_type)

### Testing
- 17 pytest tests in `tests/test_outbox_pattern.py` — all passing
- Testing agent validation: 100% success (iteration_117)
- Covers: enqueue, idempotency, transaction safety, claim protection, retry, max-retry→failed, permanent error, rollback, requeue, replay, backoff, error classification, worker metrics

---


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
