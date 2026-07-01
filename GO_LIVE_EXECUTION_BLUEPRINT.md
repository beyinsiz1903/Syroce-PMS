# GO-LIVE EXECUTION BLUEPRINT
## Enterprise PMS & Channel Manager — Production Remediation Plan

**Author**: Acting CTO / Principal Architect
**Date**: February 2026
**System**: Syroce PMS + Channel Manager (FastAPI + MongoDB + Redis)
**Target**: First real hotel pilot within 14 days

---

## 1. EXECUTIVE PRIORITY BOARD

| # | Issue | Severity | Revenue Risk | Technical Risk | User Impact | Legal/Compliance | Priority | Effort | Owner |
|---|-------|----------|-------------|---------------|------------|-----------------|----------|--------|-------|
| 1 | **No atomic availability-check + booking create** — Reservation creation checks availability in separate queries, then inserts. Two concurrent requests for the same room/dates can both succeed. | CRITICAL | **$$$** Double-sold rooms → refunds, comp stays, OTA penalties | Race condition in `create_reservation_service.py` — idempotency key protects replay, NOT concurrent different-guest bookings for same room | Guest arrives to occupied room. Trust collapse. | OTA contract violation; potential legal claims | **P0** | 3 days | Backend |
| 2 | **No MongoDB transactions on check-in/check-out** — Status update, folio creation, room status change, and OTA notification are separate writes. Partial failure leaves orphaned state. | CRITICAL | **$$** Ghost folios, revenue leakage from unposted charges | Zero `ClientSession` / `with_transaction` usage in core booking flows (`routers/pms.py` 2714 lines) | Incorrect room status shown on calendar; folio missing | Financial reporting gaps; audit failure | **P0** | 4 days | Backend |
| 3 | **OTA → PMS booking not auto-created** — Ingest pipeline (`pipeline.py`) creates lineage records but does NOT create actual PMS bookings. Reservations exist only in `reservation_lineage`, not in `bookings`. | CRITICAL | **$$$** Rooms show available when sold on OTA → double booking | Pipeline stops at lineage stage 9. No bridge to `create_reservation_service` | Staff cannot see OTA bookings in calendar/rooms view | SLA violation with OTAs | **P0** | 5 days | Backend |
| 4 | **PMS → OTA push has no guaranteed delivery** — `cm_push_event` in reservation creation is fire-and-forget (`try/except pass` on line 172). ARI outbound uses in-memory buffer. No outbox pattern for booking sync. | HIGH | **$$** PMS rate/avail changes not reflected on OTA → stale inventory or overbooking | Buffer lost on restart. `_on_buffer_flush` has no retry. Outbox worker only processes `MIGRATION_EVENT_TYPES`, not domain events | OTA shows wrong price/availability | OTA delistment risk | **P0** | 4 days | Backend |
| 5 | **Tenant isolation is policy-only, not enforced** — `tenant_isolation.py` defines rules but `enforce_tenant_filter()` is NOT called in actual query paths. Each router/service manually adds `tenant_id` to queries. One missed filter = cross-tenant data leak. | HIGH | **$** Compliance failure → contract termination | 646-line file with models and endpoints, but no middleware integration. No automated test that proves isolation. | Hotel A sees Hotel B's data | **GDPR/KVKK violation**; data breach liability | **P0** | 3 days | Backend |
| 6 | **Night audit posts charges without folio validation** — `_post_room_charges` queries `bookings` where `status=checked_in` but doesn't verify the booking has an active folio before posting. Missing `folio_id` silently skips. | HIGH | **$$** Revenue not captured for bookings without folios | `night_audit/service.py` line 249: uses `booking.get("folio_id")` which may be None | Missing nightly charges → understated revenue | Financial audit failure | **P1** | 2 days | Backend |
| 7 | **Availability check is in-memory, not indexed** — `_legacy_check_room_availability` loads ALL rooms + ALL bookings + ALL blocks into memory then filters in Python. No compound index on `(tenant_id, status, check_in, check_out)`. | HIGH | Slow availability = lost direct bookings | `.to_list(1000)` caps at 1000 — silently drops data beyond that | Slow page load on calendar/booking form | None | **P1** | 2 days | Backend |
| 8 | **Collection sprawl: 4264 unique collection references** — Code references thousands of collection names. Most are dead code from feature scaffolding. Actual DB has ~16 active collections but code paths may accidentally create new ones. | MEDIUM | Technical debt slows every change | `db.<collection>` calls without centralized registry. Any typo creates a new collection silently. | None directly | None | **P2** | 5 days | Backend + DevOps |
| 9 | **No health check beyond ping** — No deep health check that validates MongoDB connectivity, Redis availability, outbox queue depth, or background worker liveness. | MEDIUM | Undetected failures → silent data loss | `health_check.py` exists but doesn't check dependent services | Staff doesn't know system is degraded | SLA violation | **P1** | 1 day | DevOps |
| 10 | **Monolithic pms.py router: 2714 lines** — Single file handles rooms, bookings, guests, check-in, check-out, availability, housekeeping. Any change risks regression across all PMS operations. | MEDIUM | Slower dev velocity → delayed features | Circular imports, tight coupling, no unit test isolation | None directly | None | **P2** | 5 days | Backend |

---

## 2. 14-DAY GO-LIVE WAR PLAN

### Phase 1: Stop the Bleeding (Days 1-4)

| Day | Goals | Deliverables | Dependencies | Risk if Delayed |
|-----|-------|-------------|-------------|----------------|
| **Day 1** | Atomic booking with overbooking prevention | 1. `find_one_and_update` with `$inc` on room availability counter OR distributed lock around availability-check + insert. 2. Compound index on bookings `(tenant_id, room_id, status, check_in, check_out)`. 3. Concurrency test: 10 parallel booking requests for same room → exactly 1 succeeds. | MongoDB replica set for transactions (verify enabled) | **Every day without this = potential double booking** |
| **Day 2** | MongoDB transaction wrapper for check-in/check-out | 1. Transaction helper in `core/database.py`. 2. Check-in flow: update booking status + update room status + create folio charge atomically. 3. Check-out flow: update booking + room + finalize folio atomically. 4. Rollback test: force failure mid-transaction → verify clean state. | Day 1 index changes | Orphaned room states, ghost folios |
| **Day 3** | Tenant isolation middleware | 1. FastAPI middleware that injects `tenant_id` into every DB query for tenant-scoped collections. 2. Integration test: create data for Tenant A, query as Tenant B → zero results. 3. Automated scan of all `db.<collection>.find/update/delete` calls without tenant_id. | None | Cross-tenant data leak on first multi-hotel deploy |
| **Day 4** | OTA → PMS booking bridge | 1. Pipeline stage 10: after lineage CREATE/UPDATE → call `create_reservation_service` (or dedicated `import_ota_booking`). 2. Mapping resolution: room_type_code → room_id assignment logic. 3. Integration test: simulate Exely webhook → verify booking appears in `bookings` collection. | Day 1 (atomic booking) | OTA reservations invisible to front desk |

### Phase 2: Guaranteed Delivery (Days 5-8)

| Day | Goals | Deliverables | Dependencies | Risk if Delayed |
|-----|-------|-------------|-------------|----------------|
| **Day 5** | Outbox pattern for PMS → OTA sync | 1. Every booking create/modify/cancel writes to `outbox_events` with `event_type: booking.*`. 2. Extend `OutboxLifecycleWorker` to process `booking.*` events (not just migration events). 3. Remove fire-and-forget `cm_push_event` call. | Day 4 (OTA bridge) | Rate/availability changes lost on restart |
| **Day 6** | ARI outbound guaranteed delivery | 1. ARI changes write to outbox instead of in-memory buffer. 2. Push worker reads from outbox, sends to provider, marks processed/failed. 3. Dead letter queue: after 3 retries → park event, alert operator. | Day 5 (outbox extension) | Stale OTA inventory |
| **Day 7** | Night audit hardening | 1. Validate folio exists before posting charge. 2. Use transaction for charge posting. 3. Business date roll only after ALL charges posted successfully. 4. Add `dry_run` integration test that validates math. | Day 2 (transactions) | Revenue miscalculation on first live night |
| **Day 8** | Deep health checks + alerting | 1. `/api/health/deep` endpoint: MongoDB writable, Redis reachable, outbox queue depth < threshold, last night audit timestamp. 2. Prometheus metrics for outbox backlog, failed events, lock contention. 3. Alert rules: outbox > 100 pending, night audit not run by 03:00. | None | Silent failures in production |

### Phase 3: Observability & Testing (Days 9-12)

| Day | Goals | Deliverables | Dependencies | Risk if Delayed |
|-----|-------|-------------|-------------|----------------|
| **Day 9** | Concurrency test suite | 1. 10 parallel same-room bookings → 1 wins. 2. 5 parallel check-ins for same booking → 1 wins. 3. Parallel night audit trigger → only 1 runs. 4. Cross-tenant query isolation proof. | Days 1-4 fixes | No confidence in concurrent safety |
| **Day 10** | End-to-end OTA sync test | 1. Exely webhook → ingest → lineage → PMS booking → calendar visible. 2. PMS booking create → outbox → ARI push → verify Exely API called. 3. Rate change → outbox → provider push → ACK received. | Days 4-6 fixes | OTA integration untested |
| **Day 11** | Night audit + financial reconciliation test | 1. Seed 20 bookings across 3 room types. 2. Run night audit. 3. Verify: charges match room rates, taxes correct, folio balanced. 4. Run again → verify idempotency (no double charges). | Day 7 fixes | Revenue calculation wrong on go-live night |
| **Day 12** | Performance baseline | 1. Availability query < 200ms for 200 rooms. 2. Booking create < 500ms. 3. Night audit < 60s for 100 rooms. 4. Index usage verified via `explain()`. | All indexes from Days 1-7 | Slow system under real load |

### Phase 4: Go-Live Prep (Days 13-14)

| Day | Goals | Deliverables | Dependencies | Risk if Delayed |
|-----|-------|-------------|-------------|----------------|
| **Day 13** | Staging dry run | 1. Full cycle: seed hotel data → create bookings → run night audit → verify reports. 2. OTA webhook simulation (10 reservations). 3. Tenant isolation smoke test with 2 hotels. 4. Monitoring dashboards operational. | All previous | Untested in staging |
| **Day 14** | Go/No-Go decision + cutover plan | 1. Go-live gate checklist (Section 8) — all blockers green. 2. Rollback procedure documented and tested. 3. On-call rotation established. 4. First hotel data migration script ready. | Day 13 staging pass | Rushed go-live = incident |

---

## 3. ENGINEERING BACKLOG

### 3.1 Booking Integrity

#### BOOK-001: Atomic Availability Check + Booking Create
- **Problem**: `create_reservation_service.py` checks availability via separate query, then inserts. Race window between check and insert allows double booking.
- **Business reason**: A double-booked room costs ~$200 in compensation + OTA penalty + trust damage.
- **Technical approach**: Use distributed lock (`infra/distributed_lock.py`) scoped to `room_id:date_range`. Lock → check availability → insert → release. Alternatively, use MongoDB `findOneAndUpdate` with availability counter.
- **Definition of done**: 10 concurrent booking attempts for same room/date → exactly 1 succeeds, 9 get HTTP 409.
- **Files**: `modules/reservations/services/create_reservation_service.py`, `modules/inventory/repository.py`, `infra/distributed_lock.py`
- **Test**: `pytest tests/test_booking_concurrency.py` — 10 parallel async requests
- **Rollback**: Remove lock wrapper, revert to current behavior

#### BOOK-002: Check-in/Check-out Transaction Safety
- **Problem**: Check-in updates booking status, room status, and creates folio entries as separate writes. Failure between writes leaves inconsistent state.
- **Business reason**: Guest checks in but room still shows "available" → another guest assigned same room.
- **Technical approach**: MongoDB multi-document transaction via `ClientSession`. Wrap: (1) update booking.status, (2) update room.status, (3) insert folio charge in single transaction.
- **Definition of done**: Simulated failure after booking update but before room update → both rolled back.
- **Files**: `routers/pms.py` (check_in/check_out handlers), `core/database.py` (transaction helper)
- **Test**: Integration test with fault injection
- **Rollback**: Remove transaction wrapper, revert to sequential writes

#### BOOK-003: Overbooking Detection on Every Write Path
- **Problem**: Availability checked on UI booking flow, but NOT on OTA import, group booking, or room block creation.
- **Business reason**: OTA booking imported without availability check → physical overbooking.
- **Technical approach**: Centralized `assert_room_available(tenant_id, room_id, check_in, check_out)` called from ALL booking creation paths.
- **Definition of done**: Import OTA booking for occupied room → rejected with clear error.
- **Files**: `modules/inventory/services/availability_read_service.py`, `domains/channel_manager/ingest/pipeline.py`
- **Test**: Unit test + integration test for each entry point
- **Rollback**: Remove check (unsafe but possible)

---

### 3.2 OTA/Channel Sync

#### OTA-001: OTA → PMS Automatic Booking Import
- **Problem**: Ingest pipeline creates `reservation_lineage` but never creates a `bookings` document. Front desk cannot see OTA reservations.
- **Business reason**: 60-80% of hotel bookings come via OTAs. If they're invisible, hotel is operationally blind.
- **Technical approach**: Add Stage 10 to `pipeline.py`: on CREATE/UPDATE decision, call a new `import_ota_booking_service` that maps lineage data → BookingCreate schema → `create_reservation_service.create()`.
- **Definition of done**: Exely webhook fires → reservation visible in PMS calendar within 30 seconds.
- **Files**: `domains/channel_manager/ingest/pipeline.py`, new `domains/channel_manager/ingest/pms_bridge.py`, `modules/reservations/services/create_reservation_service.py`
- **Test**: End-to-end: POST to Exely webhook endpoint → poll bookings → assert new booking exists
- **Rollback**: Disable Stage 10 flag

#### OTA-002: PMS → OTA Guaranteed Delivery via Outbox
- **Problem**: `cm_push_event` call in `create_reservation_service.py:172` is wrapped in `try/except pass`. If it fails, OTA never learns about the booking.
- **Business reason**: Room sold on PMS but OTA still shows available → double sell.
- **Technical approach**: Replace fire-and-forget with outbox write. Extend `OutboxLifecycleWorker.MIGRATION_EVENT_TYPES` to include `booking.created`, `booking.modified`, `booking.cancelled`, `ari.*`. Worker reads, pushes to provider, ACKs or retries.
- **Definition of done**: Kill the push mid-flight → event stays in outbox → retried automatically → delivered.
- **Files**: `shared_kernel/outbox_lifecycle.py`, `modules/reservations/services/create_reservation_service.py`, `domains/channel_manager/ari/outbound_service.py`
- **Test**: Insert outbox event → verify worker picks up and calls provider adapter
- **Rollback**: Revert to fire-and-forget (unsafe but functional)

#### OTA-003: ARI Push Persistence
- **Problem**: ARI outbound service uses in-memory `ARIEventBuffer`. On process restart, buffered events are lost.
- **Business reason**: Rate update made by revenue manager → process restarts → OTA shows old rate → revenue loss.
- **Technical approach**: Write ARI events to `outbox_events` with `event_type: ari.push`. Remove in-memory buffer. Outbox worker handles push.
- **Definition of done**: ARI event survives process restart and is delivered.
- **Files**: `domains/channel_manager/ari/outbound_service.py`, `domains/channel_manager/ari/buffer.py`, `shared_kernel/outbox_lifecycle.py`
- **Test**: Publish ARI event → restart backend → verify event delivered
- **Rollback**: Re-enable in-memory buffer

---

### 3.3 Night Audit

#### NA-001: Folio Validation Before Charge Posting
- **Problem**: `_post_room_charges` uses `booking.get("folio_id")` which may be None. Charge is created with null folio_id.
- **Business reason**: Revenue posted to null folio → invisible in accounting → financial misstatement.
- **Technical approach**: Before posting charge, verify folio exists via `db.folios.find_one({id: folio_id})`. If missing, create folio first (same as reservation creation flow), then post charge. Log exception if folio creation needed.
- **Definition of done**: Booking without folio → folio auto-created → charge posted → exception logged.
- **Files**: `domains/pms/night_audit/service.py` lines 212-280
- **Test**: Seed booking without folio_id → run night audit → verify folio created + charge posted
- **Rollback**: Revert validation (charges post to null folio again)

#### NA-002: Transactional Charge Posting
- **Problem**: Each nightly charge is an individual insert. If 50 out of 100 succeed before a crash, business date still rolls forward on next run attempt.
- **Business reason**: Partial charge posting + business date roll = unrecoverable state.
- **Technical approach**: Batch all charge inserts in a single transaction. Only roll business date if ALL charges committed. Use the audit run record as checkpoint.
- **Definition of done**: Simulated crash at charge 50/100 → rerun posts all 100 charges correctly.
- **Files**: `domains/pms/night_audit/service.py`
- **Test**: Fault injection test
- **Rollback**: Remove transaction, revert to per-charge insert

---

### 3.4 Tenant Isolation

#### TI-001: Query-Level Tenant Enforcement Middleware
- **Problem**: `TenantIsolationEngine.enforce_tenant_filter()` exists but is never called in actual query paths. Each service/router manually adds `tenant_id`. One miss = data leak.
- **Business reason**: Multi-hotel deployment requires ironclad isolation. KVKK/GDPR liability.
- **Technical approach**: FastAPI middleware that intercepts database proxy. Wrap `db` access with a tenant-aware proxy that auto-injects `tenant_id` for all tenant-scoped collections. Alternatively: create `TenantScopedDB` class that requires `tenant_id` at construction.
- **Definition of done**: Remove `tenant_id` from a query manually → middleware adds it back. Cross-tenant query → blocked + logged.
- **Files**: `tenant_isolation.py`, `core/database.py`, `server.py`
- **Test**: Dedicated test: query as Tenant A, verify zero Tenant B data returned
- **Rollback**: Remove middleware, revert to manual tenant_id injection

#### TI-002: Tenant Isolation Proof Test Suite
- **Problem**: No automated test proves tenant isolation works.
- **Business reason**: Cannot promise enterprise customers their data is safe without proof.
- **Technical approach**: Test creates 2 tenants, seeds identical data for both, queries each → verifies zero cross-contamination across: bookings, guests, rooms, folios, payments.
- **Definition of done**: `pytest tests/test_tenant_isolation_proof.py` — 10+ assertions, all green.
- **Files**: New `tests/test_tenant_isolation_proof.py`
- **Test**: The test IS the deliverable
- **Rollback**: N/A

---

### 3.5 Performance

#### PERF-001: Compound Indexes for Hot Queries
- **Problem**: No compound indexes on bookings, rooms, or folios for common query patterns. All queries do collection scans.
- **Business reason**: Slow availability check = lost bookings. Slow calendar = staff frustration.
- **Technical approach**: Create indexes:
  - `bookings: (tenant_id, room_id, status, check_in, check_out)`
  - `bookings: (tenant_id, status, check_in)`
  - `rooms: (tenant_id, is_active, room_type)`
  - `folios: (tenant_id, booking_id)`
  - `outbox_events: (status, event_type, created_at)`
- **Definition of done**: `explain()` shows IXSCAN (not COLLSCAN) for top 5 queries.
- **Files**: `startup.py` or new `core/indexes.py`
- **Test**: Run `explain()` on hot queries, verify index usage
- **Rollback**: Drop indexes (safe, just slower)

#### PERF-002: Availability Query Optimization
- **Problem**: `_legacy_check_room_availability` loads all rooms, bookings, blocks into memory. `.to_list(1000)` silently drops data.
- **Business reason**: Hotel with 300 rooms + 1000 bookings = slow + incorrect.
- **Technical approach**: Replace with aggregation pipeline: `$lookup` rooms against bookings for date range, compute availability server-side. Remove `.to_list(1000)` cap.
- **Definition of done**: Availability for 300 rooms in < 200ms.
- **Files**: `modules/inventory/services/availability_read_service.py`, `routers/pms.py`
- **Test**: Load test with 300 rooms, 500 active bookings
- **Rollback**: Revert to current in-memory approach

---

### 3.6 Observability

#### OBS-001: Deep Health Check Endpoint
- **Problem**: No way to know if MongoDB, Redis, outbox, or background workers are healthy.
- **Technical approach**: `/api/health/deep` returns: `{mongo: ok/fail, redis: ok/fail, outbox_pending: N, last_night_audit: datetime, worker_alive: bool}`
- **Files**: `health_check.py`
- **Test**: Kill Redis → health check returns `redis: fail`
- **Rollback**: Remove endpoint

#### OBS-002: Outbox Dashboard Metrics
- **Problem**: No visibility into outbox queue depth, failed events, or parked events.
- **Technical approach**: Prometheus counters: `outbox_events_pending`, `outbox_events_failed`, `outbox_events_parked`, `outbox_processing_duration_seconds`. Expose via `/api/metrics`.
- **Files**: `shared_kernel/outbox_lifecycle.py`, `prometheus_metrics.py`
- **Test**: Verify metrics increment after event processing
- **Rollback**: Remove metric registration

---

### 3.7 Security

#### SEC-001: PII Masking in Logs
- **Problem**: Guest names, emails, phone numbers may appear in log output from pipeline and service layers.
- **Technical approach**: Create `sanitize_for_log(data)` utility that masks PII fields before logging. Apply to all `logger.info/warning/error` calls that include guest data.
- **Files**: New `shared_kernel/log_sanitizer.py`, applied across services
- **Test**: Grep logs after test run → zero raw PII
- **Rollback**: Remove sanitizer

---

### 3.8 Infrastructure

#### INFRA-001: MongoDB Index Initialization on Startup
- **Problem**: Indexes not guaranteed to exist on fresh deployment.
- **Technical approach**: `startup.py` calls `ensure_indexes()` on every boot. Idempotent (`create_index` is a no-op if index exists).
- **Files**: `startup.py`, new `core/indexes.py`
- **Test**: Fresh DB → start app → verify indexes exist
- **Rollback**: Remove startup call

#### INFRA-002: Collection Registry
- **Problem**: 4264 collection name references scattered across code. Typos create phantom collections.
- **Technical approach**: Create `core/collections.py` with `BOOKINGS = "bookings"`, `ROOMS = "rooms"`, etc. Grep and replace all string literals. Lint rule: ban `db["<string>"]` and `db.<string>` outside registry.
- **Files**: New `core/collections.py`, all files using `db.<collection>`
- **Test**: `grep -rn 'db\.\w\+' --include="*.py" | grep -v collections.py` → should be zero
- **Rollback**: Revert to string literals

---

## 4. P0 FIXES — DEEP IMPLEMENTATION DESIGN

### P0-FIX-1: Atomic Availability Check + Booking Create

**Current broken flow:**
```
1. Client sends POST /api/bookings
2. create_reservation_service.create() acquires IDEMPOTENCY lock (protects replay, NOT concurrency)
3. get_room_for_tenant() verifies room exists
4. get_guest_for_tenant() verifies guest exists
5. ⚠️ NO availability check here — room may already be booked for these dates
6. insert_booking() → booking created
7. Two concurrent requests for same room/dates: BOTH succeed
```

**Target fixed flow:**
```
1. Client sends POST /api/bookings
2. Acquire DISTRIBUTED LOCK: key = "booking:{tenant_id}:{room_id}:{check_in}:{check_out}"
3. Inside lock:
   a. Check conflicting bookings: db.bookings.find({tenant_id, room_id, status in [confirmed,checked_in,guaranteed], overlapping dates})
   b. If conflict → HTTP 409 Conflict
   c. If clear → insert_booking()
4. Release lock
5. Second concurrent request: blocked by lock → when lock released, finds conflict → 409
```

**Architecture pattern:** Pessimistic locking via distributed lock (already exists in `infra/distributed_lock.py`)

**Code-level strategy:**
```python
# In create_reservation_service.py, after idempotency check:

from infra.distributed_lock import lock_manager

async def create(self, booking_data, current_user, request):
    # ... existing idempotency check ...
    
    # STEP: Acquire room-date lock
    lock_key = f"room_booking:{tenant_context.tenant_id}:{booking_data.room_id}:{booking_data.check_in}:{booking_data.check_out}"
    async with lock_manager.lock(lock_key, timeout=10.0, tenant_id=tenant_context.tenant_id):
        # STEP: Check for conflicting bookings
        conflicts = await self.repository.list_conflicting_bookings(
            tenant_id=tenant_context.tenant_id,
            room_id=booking_data.room_id,
            start_date=booking_data.check_in,
            end_date=booking_data.check_out,
        )
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Room already booked for overlapping dates. Conflicting booking: {conflicts[0].get('id')}"
            )
        
        # STEP: Proceed with booking creation (existing code)
        await self.repository.insert_booking(booking_dict)
```

**Data model changes:**
- Add compound index: `bookings (tenant_id, room_id, status, check_in, check_out)`
- No schema changes needed

**Edge cases:**
- Redis unavailable → falls back to asyncio.Lock (in-process only, safe for single instance, NOT safe for multi-instance)
- Lock timeout (10s) too short for slow DB → extend to 15s with monitoring
- Same guest, same room, adjacent dates (check-out = next check-in) → NOT a conflict, ensure `$lt/$gt` not `$lte/$gte`

**Testing requirements:**
1. Unit: Mock repository, verify lock acquisition + conflict check
2. Concurrency: 10 parallel asyncio tasks booking same room → exactly 1 succeeds
3. Edge: Adjacent dates (not overlapping) → both succeed
4. Failure: Force lock timeout → verify clean error response

---

### P0-FIX-2: MongoDB Transaction Strategy for Check-in/Check-out

**Current broken flow:**
```
# In routers/pms.py check-in handler:
1. db.bookings.update_one({id: booking_id}, {$set: {status: "checked_in"}})
2. db.rooms.update_one({id: room_id}, {$set: {status: "occupied"}})
3. Optional: create folio entry
# If step 2 fails: booking says checked_in but room says available
```

**Target fixed flow:**
```
async with get_transaction_session() as session:
    await db.bookings.update_one(
        {id: booking_id, tenant_id: tid},
        {$set: {status: "checked_in", checked_in_at: now}},
        session=session
    )
    await db.rooms.update_one(
        {id: room_id, tenant_id: tid},
        {$set: {status: "occupied", current_booking_id: booking_id}},
        session=session
    )
    await db.folios.update_one(
        {booking_id: booking_id, tenant_id: tid},
        {$set: {status: "open"}},
        session=session
    )
# All succeed or all fail. No orphaned states.
```

**Architecture pattern:** MongoDB multi-document transactions (requires replica set)

**Code-level strategy:**
```python
# core/database.py - add transaction helper

from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient

@asynccontextmanager
async def transaction():
    """Provide a MongoDB transaction session."""
    async with db.client.start_session() as session:
        async with session.start_transaction():
            yield session
```

**Data model changes:** None — MongoDB transactions work on existing collections. Requires replica set (single-node replica set is acceptable for development).

**Edge cases:**
- MongoDB standalone (no replica set) → transactions fail. MUST configure as single-node replica set at minimum.
- Transaction timeout (default 60s) — check-in should complete in < 5s.
- Write conflict (another transaction touching same document) → automatic retry (configurable).
- Session must be passed to EVERY operation within the transaction — missed operation = outside transaction.

**Testing requirements:**
1. Happy path: check-in completes, all 3 documents updated
2. Fault injection: raise exception after booking update → verify room NOT updated
3. Concurrent: 2 check-in requests for same booking → 1 succeeds, 1 gets 409
4. Verify: MongoDB standalone fails gracefully with clear error message

---

### P0-FIX-3: OTA → PMS Automatic Booking Import

**Current broken flow:**
```
1. Exely webhook → raw_channel_events
2. pipeline.process_event() → stages 2-9
3. Stage 9: _create_lineage() → reservation_lineage document created
4. ❌ NO Stage 10: lineage NOT bridged to bookings collection
5. Front desk opens calendar → OTA booking NOT visible
```

**Target fixed flow:**
```
1. Exely webhook → raw_channel_events
2. pipeline.process_event() → stages 2-9
3. Stage 9: _create_lineage() → lineage created
4. Stage 10 (NEW): _bridge_to_pms()
   a. Resolve room_type_code → available room_id (using mapping + availability)
   b. Resolve rate_plan_code → rate_plan (using mapping)
   c. Find or create guest by email/phone
   d. Call create_reservation_service with origin="ota"
   e. Update lineage with pms_booking_id
   f. If room unavailable → create reconciliation case (overbooking risk)
5. Front desk sees booking immediately
```

**Architecture pattern:** Event-driven bridge with idempotency

**Code-level strategy:**
```python
# New file: domains/channel_manager/ingest/pms_bridge.py

async def bridge_lineage_to_pms(lineage: dict, canonical: dict, tenant_id: str, property_id: str) -> Optional[str]:
    """Create PMS booking from confirmed OTA lineage. Returns booking_id or None."""
    
    # 1. Check if already bridged (idempotent)
    if lineage.get("pms_booking_id"):
        return lineage["pms_booking_id"]
    
    # 2. Resolve room mapping → find available room of that type
    room_type_mapping = await get_pms_room_type(tenant_id, property_id, canonical["room_type_code"])
    if not room_type_mapping:
        raise MappingNotFoundError(f"No PMS room type for {canonical['room_type_code']}")
    
    available_room = await find_available_room(
        tenant_id, room_type_mapping["pms_room_type"],
        canonical["check_in"], canonical["check_out"]
    )
    if not available_room:
        # CRITICAL: OTA sold room we don't have → create overbooking case
        await create_overbooking_case(tenant_id, property_id, canonical)
        return None
    
    # 3. Find or create guest
    guest_id = await find_or_create_guest(tenant_id, canonical)
    
    # 4. Create PMS booking
    booking_data = BookingCreate(
        room_id=available_room["id"],
        guest_id=guest_id,
        check_in=canonical["check_in"],
        check_out=canonical["check_out"],
        total_amount=canonical.get("total_amount", 0),
        source_channel="ota",
        origin="channel_manager",
        ota_channel=canonical.get("source_system"),
        ota_reference_id=canonical.get("external_reservation_id"),
    )
    
    result = await create_reservation_service.create(booking_data, system_user, fake_request)
    
    # 5. Link lineage to PMS booking
    await repo.update_lineage_pms_link(lineage["id"], result["id"])
    return result["id"]
```

**Data model changes:**
- Add `pms_booking_id` field to `reservation_lineage` schema
- Add `source_lineage_id` field to `bookings` schema
- Add index: `reservation_lineage (tenant_id, pms_booking_id)`

**Edge cases:**
- Room type mapped but no available room → overbooking case created, front desk alerted
- Guest email not provided by OTA → create with placeholder, flag for review
- Modification comes before initial create processed → version check prevents stale update
- Cancellation for not-yet-imported booking → process create first, then cancel
- Rate plan not mapped → booking created with OTA rate, flagged for rate review

**Testing requirements:**
1. Happy path: webhook → lineage → booking → visible in calendar
2. No available room → overbooking case created
3. Duplicate webhook → idempotent (no duplicate booking)
4. Modification → existing booking updated
5. Cancellation → booking cancelled in PMS

---

### P0-FIX-4: PMS → OTA Guaranteed Delivery / Outbox

**Current broken flow:**
```python
# create_reservation_service.py line 155-173
try:
    from server import cm_push_event as _cm_push
    await _cm_push({...})
except Exception:
    pass  # ← SILENT FAILURE. OTA never learns about this booking.
```

**Target fixed flow:**
```python
# Instead of fire-and-forget push:
outbox_doc = {
    "event_id": str(uuid.uuid4()),
    "event_type": "booking.created",
    "tenant_id": tenant_context.tenant_id,
    "payload": {
        "booking_id": booking_id,
        "room_id": booking_data.room_id,
        "check_in": booking_data.check_in,
        "check_out": booking_data.check_out,
        "status": "confirmed",
    },
    "status": "pending",
    "created_at": iso_now(),
    "retry_count": 0,
}
await db.outbox_events.insert_one(outbox_doc)
# OutboxLifecycleWorker picks this up, pushes to OTA, marks processed
```

**Architecture pattern:** Transactional Outbox

**Code-level strategy:**
1. Remove `cm_push_event` fire-and-forget call
2. Write outbox event in same "logical unit" as booking creation
3. Extend `OutboxLifecycleWorker`:
   - Add `booking.created`, `booking.modified`, `booking.cancelled`, `ari.push` to event type filter
   - In `handle_event()`: dispatch to provider-specific adapter based on event_type
   - On success: mark processed
   - On failure: retry with backoff (existing logic works)
   - After max retries: park + alert

**Data model changes:**
- `outbox_events`: add `event_type` values for `booking.*` and `ari.*`
- Add index: `outbox_events (event_type, status, created_at)`

**Edge cases:**
- Provider API down → events accumulate in outbox → backpressure alert at 100+ pending
- Provider returns partial success (3 of 5 rooms updated) → track per-room ACK
- Outbox worker restart during processing → `recover_stuck_processing` handles it (existing)
- Event ordering: modifications must be applied in order → use `created_at` sort (existing)

**Testing requirements:**
1. Create booking → verify outbox event created
2. Start worker → verify provider adapter called
3. Force provider failure → verify retry
4. 3 failures → verify parked + alert
5. Process restart mid-delivery → verify no duplicate push

---

### P0-FIX-5: Tenant Isolation Enforcement

**Current broken flow:**
```python
# tenant_isolation.py has TenantIsolationEngine with enforce_tenant_filter()
# BUT: it's NEVER used in actual query paths
# Every service/router manually does: {"tenant_id": current_user.tenant_id}
# One missed filter = cross-tenant data leak

# Example from routers/pms.py:
rooms = await db.rooms.find({'tenant_id': tenant_id}, {'_id': 0}).to_list(1000)
# What if someone forgets tenant_id? → sees ALL hotels' rooms
```

**Target fixed flow:**
```python
# New: TenantScopedDB wrapper
class TenantScopedDB:
    def __init__(self, db, tenant_id: str):
        self._db = db
        self._tenant_id = tenant_id
    
    def __getattr__(self, collection_name: str):
        if collection_name in TENANT_SCOPED_COLLECTIONS:
            return TenantScopedCollection(self._db[collection_name], self._tenant_id)
        return self._db[collection_name]  # global collections pass through

class TenantScopedCollection:
    def __init__(self, collection, tenant_id):
        self._coll = collection
        self._tenant_id = tenant_id
    
    def find(self, filter=None, *args, **kwargs):
        filter = filter or {}
        filter["tenant_id"] = self._tenant_id  # ALWAYS injected
        return self._coll.find(filter, *args, **kwargs)
    
    # Same for find_one, update_one, update_many, delete_one, delete_many, aggregate

# Usage in routes:
@router.get("/api/rooms")
async def get_rooms(current_user = Depends(get_current_user)):
    tdb = TenantScopedDB(db, current_user.tenant_id)
    rooms = await tdb.rooms.find({}, {"_id": 0}).to_list(1000)
    # tenant_id automatically injected — impossible to forget
```

**Architecture pattern:** Database proxy / query interceptor

**Code-level strategy:**
1. Create `core/tenant_db.py` with `TenantScopedDB` and `TenantScopedCollection`
2. Add FastAPI dependency: `get_tenant_db(current_user) → TenantScopedDB`
3. Migrate routes one module at a time (start with `bookings`, `rooms`, `guests`)
4. Add strict mode: log WARNING for any direct `db.<collection>` access in tenant context

**Data model changes:** None

**Edge cases:**
- Super admin needs cross-tenant access → bypass method: `tdb.raw()` returns unwrapped db
- Aggregation pipelines with `$lookup` → `$match` stage must include `tenant_id`
- Background workers without user context → pass tenant_id explicitly
- Bulk operations (night audit processes all checked_in bookings) → scoped by tenant_id already

**Testing requirements:**
1. Create Tenant A data, query as Tenant B → zero results
2. Attempt to update Tenant A booking as Tenant B → blocked
3. Super admin cross-tenant → works
4. Direct `db.bookings.find({})` without tenant → returns all (proves middleware is needed)
5. `TenantScopedDB` find → returns only current tenant's data

---

## 5. DATA MODEL REPAIR PLAN

### Current State
- **Code references**: ~4264 unique `db.<collection>` patterns found
- **Active MongoDB collections**: 16 (most are created on-demand)
- **Problem**: Massive collection name sprawl in code creates confusion, no single source of truth

### Consolidation Plan

#### Collections That MUST Remain Separate (Core Domain)
| Collection | Reason | Required Indexes |
|-----------|--------|-----------------|
| `bookings` | Core entity, high write volume | `(tenant_id, room_id, status, check_in, check_out)`, `(tenant_id, status, check_in)`, `(tenant_id, guest_id)` |
| `rooms` | Core entity, medium write | `(tenant_id, is_active, room_type)`, `(tenant_id, id)` unique |
| `guests` | Core entity, PII | `(tenant_id, email)`, `(tenant_id, phone)` |
| `folios` | Financial, audit trail | `(tenant_id, booking_id)`, `(tenant_id, status)` |
| `folio_charges` | Financial detail | `(tenant_id, folio_id)`, `(tenant_id, booking_id)` |
| `payments` | Financial, reconciliation | `(tenant_id, folio_id)`, `(tenant_id, booking_id)` |
| `users` | Auth, multi-tenant | `(tenant_id, email)` unique, `(tenant_id, role)` |
| `tenants` | Global, no tenant_id filter | `(id)` unique |
| `tenant_settings` | Per-tenant config | `(tenant_id)` unique |

#### Collections That Should Be Consolidated

| Current (Scattered) | Consolidate Into | Strategy |
|---------------------|-----------------|----------|
| `housekeeping_tasks`, `cleaning_requests`, `maintenance_orders` | `operations_tasks` | Add `task_type` field: `housekeeping`, `cleaning`, `maintenance` |
| `audit_logs`, `tenant_access_logs`, `data_access_logs` | `audit_trail` | Add `log_type` field |
| `night_audit_runs`, `night_audit_exceptions` | Keep separate | Night audit needs its own lifecycle |
| `rate_plans`, `rate_override_logs` | Keep separate | Different access patterns |
| `invoices`, `invoice_items` | Keep separate | Financial audit requirement |
| `channel_sync_logs`, `raw_channel_events` | Keep separate | High volume, different retention |

#### Collections That Should Become Embedded Documents

| Current Collection | Embed Into | Reason |
|-------------------|-----------|--------|
| `booking_notes` | `bookings.notes[]` | Always accessed with booking |
| `room_amenities` | `rooms.amenities[]` | Always read with room |
| `guest_preferences` | `guests.preferences{}` | Always read with guest |
| `folio_adjustments` | `folios.adjustments[]` | Always accessed with folio |

#### Collections Requiring JSON Schema Validation

| Collection | Critical Fields | Validation |
|-----------|----------------|------------|
| `bookings` | `tenant_id`, `room_id`, `guest_id`, `check_in`, `check_out`, `status` | Required, type enforcement |
| `folios` | `tenant_id`, `booking_id`, `folio_number`, `status` | Required, type enforcement |
| `payments` | `tenant_id`, `folio_id`, `amount`, `payment_method` | Required, type + range |
| `outbox_events` | `event_id`, `event_type`, `status`, `tenant_id` | Required, enum for status |

#### Collections Requiring Compound Indexes

See individual entries above. Summary of CRITICAL indexes to create on Day 1:

```javascript
// Run in MongoDB shell or startup.py
db.bookings.createIndex(
  { tenant_id: 1, room_id: 1, status: 1, check_in: 1, check_out: 1 },
  { name: "idx_booking_availability" }
);
db.bookings.createIndex(
  { tenant_id: 1, status: 1, check_in: 1 },
  { name: "idx_booking_tenant_status_date" }
);
db.rooms.createIndex(
  { tenant_id: 1, id: 1 },
  { name: "idx_room_tenant_id", unique: true }
);
db.folios.createIndex(
  { tenant_id: 1, booking_id: 1 },
  { name: "idx_folio_tenant_booking" }
);
db.outbox_events.createIndex(
  { status: 1, event_type: 1, created_at: 1 },
  { name: "idx_outbox_pending_dispatch" }
);
db.reservation_lineage.createIndex(
  { tenant_id: 1, provider: 1, external_reservation_id: 1 },
  { name: "idx_lineage_lookup", unique: true }
);
```

### Dead Code Collections to Delete References For
Any `db.<name>` reference where:
1. No test writes to it
2. No API reads from it
3. No seed data populates it

Target: Reduce 4264 references to < 50 known, registered collection names.

---

## 6. OBSERVABILITY & INCIDENT RESPONSE PLAN

### Health Checks

| Check | Endpoint | Interval | Failure Action |
|-------|----------|----------|---------------|
| **MongoDB writable** | `POST /api/health/deep` | 30s | Page on-call |
| **Redis reachable** | `POST /api/health/deep` | 30s | Log WARNING, continue (graceful degradation) |
| **Outbox queue depth** | `GET /api/health/outbox` | 60s | Alert if > 50 pending |
| **Night audit status** | `GET /api/health/night-audit` | Hourly after 00:00 | Alert if not completed by 03:00 |
| **Background worker alive** | `GET /api/health/workers` | 60s | Restart worker |

### Required Alerts

| Alert | Trigger | Severity | Channel |
|-------|---------|----------|---------|
| **Overbooking detected** | Booking created for occupied room/dates | CRITICAL | SMS + Slack |
| **Outbox backlog** | > 100 pending events for > 5 minutes | HIGH | Slack |
| **Night audit failure** | Status = "failed" | CRITICAL | SMS + Slack |
| **Night audit not started** | 03:00 local time, no run for current business date | HIGH | Slack |
| **OTA push failure** | 3 consecutive failed pushes to same provider | HIGH | Slack |
| **Cross-tenant access attempt** | Query without tenant_id on scoped collection | CRITICAL | Slack + audit log |
| **Redis degraded** | Fallback to in-process locks | MEDIUM | Slack |
| **Lock contention** | > 5 lock failures in 1 minute | MEDIUM | Dashboard |
| **Dead letter queue** | Any event parked in outbox | MEDIUM | Slack daily digest |

### Dashboard Metrics

| Metric | Type | Dashboard |
|--------|------|-----------|
| `bookings_created_total` | Counter | Operations |
| `bookings_by_channel` | Counter (label: channel) | Operations |
| `checkins_today` | Gauge | Front desk |
| `checkouts_today` | Gauge | Front desk |
| `occupancy_rate` | Gauge | GM dashboard |
| `availability_query_duration_ms` | Histogram | Performance |
| `booking_create_duration_ms` | Histogram | Performance |
| `night_audit_duration_ms` | Histogram | Operations |
| `outbox_pending_count` | Gauge | Infrastructure |
| `outbox_failed_count` | Gauge | Infrastructure |
| `outbox_parked_count` | Gauge | Infrastructure |
| `ota_push_success_rate` | Gauge (per provider) | Channel Manager |
| `ota_push_latency_ms` | Histogram | Channel Manager |
| `lock_acquisitions_total` | Counter | Infrastructure |
| `lock_failures_total` | Counter | Infrastructure |
| `active_locks` | Gauge | Infrastructure |

### Audit Visibility
- Every booking create/modify/cancel → audit_trail entry with actor, timestamp, before/after state
- Every OTA sync event → raw_channel_events + lineage update
- Every night audit run → night_audit_runs with full exception details
- Every payment → audit_trail with amount, method, folio_id

### Failed OTA Sync Visibility
- Dashboard: List of outbox events with status=failed or status=parked
- Filter by: provider, event_type, date range
- Action: manual retry button, manual resolve button
- Alert: daily digest of unresolved failed syncs

### Night Audit Failure Alert
- Monitor: `night_audit_runs.status = "failed"` → immediate alert
- Monitor: no `night_audit_runs` document for current business date by 03:00 → alert
- Dashboard: last 7 days of audit runs with status, duration, exception count

### Redis Degraded Mode Visibility
- Health check reports `redis: degraded` when using fallback locks
- Dashboard shows lock type distribution (redis vs fallback)
- Alert: any fallback lock usage in production = immediate investigation

### Dead Letter Queue Visibility
- Dashboard: count of parked outbox events, grouped by event_type
- Each parked event shows: event_id, created_at, last_error, retry_count
- Action: "Replay" button to reset status to pending and retry

---

## 7. TEST EXECUTION MATRIX

| # | Test Name | Category | What It Validates | Pass Criteria | Automation | Environment |
|---|-----------|----------|-------------------|---------------|-----------|-------------|
| 1 | **Concurrent same-room booking** | Concurrency | Only 1 of N parallel requests succeeds | Exactly 1 HTTP 201, rest HTTP 409 | Automated (pytest + asyncio) | Local |
| 2 | **Check-in transaction rollback** | Transaction | Partial failure rolls back all changes | Room status unchanged after failed check-in | Automated (fault injection) | Local |
| 3 | **Check-out transaction rollback** | Transaction | Same as above for check-out | Booking status unchanged after failed checkout | Automated | Local |
| 4 | **OTA webhook → PMS booking** | Integration | Full pipeline: webhook → lineage → booking | Booking in `bookings` collection within 30s | Automated | Staging |
| 5 | **PMS booking → OTA push** | Integration | Outbox → provider adapter called | Provider mock received push within 60s | Automated | Staging |
| 6 | **Outbox retry on failure** | Integration | Failed push retried with backoff | Event status transitions: pending → failed → pending → processed | Automated | Local |
| 7 | **Outbox dead letter** | Integration | After max retries, event parked | Event status = parked after 3 failures | Automated | Local |
| 8 | **Night audit charge accuracy** | Functional | Room charges match rate × tax | Sum of charges = expected total ± 0.01 | Automated | Local |
| 9 | **Night audit idempotency** | Functional | Re-run doesn't duplicate charges | Charge count unchanged after re-run | Automated | Local |
| 10 | **Night audit folio validation** | Functional | Missing folio detected and created | Exception logged, folio created, charge posted | Automated | Local |
| 11 | **Tenant isolation: read** | Security | Tenant B cannot read Tenant A data | Zero documents returned for cross-tenant query | Automated | Local |
| 12 | **Tenant isolation: write** | Security | Tenant B cannot modify Tenant A data | Update matched_count = 0 for cross-tenant update | Automated | Local |
| 13 | **Tenant isolation: aggregation** | Security | Pipeline respects tenant boundaries | Aggregation result contains only own tenant data | Automated | Local |
| 14 | **Overbooking simulation** | Concurrency | 50 bookings for 10 rooms → no overbooking | Max confirmed bookings per room per night = 1 | Automated | Staging |
| 15 | **OTA sync reconciliation** | Integration | PMS and OTA state match after sync cycle | Rate/availability delta = 0 after full sync | Semi-automated | Staging |
| 16 | **Night audit under load** | Performance | 100 rooms processed < 60s | Audit duration < 60,000ms | Automated (k6) | Staging |
| 17 | **Availability query performance** | Performance | 200 rooms, 500 bookings < 200ms | p95 < 200ms | Automated (k6) | Staging |
| 18 | **Booking create performance** | Performance | < 500ms under normal load | p95 < 500ms | Automated (k6) | Staging |
| 19 | **Redis failover** | Failover | System continues with degraded locks when Redis down | Bookings still created (with warning log) | Manual | Staging |
| 20 | **MongoDB connection loss** | Failover | Graceful error, no data corruption | 503 response, no partial writes | Manual | Staging |

---

## 8. GO-LIVE GATE CHECKLIST

### BLOCKERS (Do NOT go live if ANY is red)

| # | Gate | Status | Verified By |
|---|------|--------|------------|
| B1 | Atomic booking prevents double-sell | ⬜ | Concurrency test passes |
| B2 | Check-in/check-out uses transactions | ⬜ | Transaction rollback test passes |
| B3 | OTA bookings visible in PMS | ⬜ | End-to-end webhook test |
| B4 | PMS changes push to OTA via outbox | ⬜ | Outbox delivery test |
| B5 | Tenant isolation proven with test | ⬜ | Isolation test suite green |
| B6 | Night audit posts correct charges | ⬜ | Math verification test |
| B7 | Night audit idempotent | ⬜ | Re-run test |
| B8 | Health check endpoint operational | ⬜ | Manual verification |
| B9 | MongoDB indexes created for hot queries | ⬜ | `explain()` shows IXSCAN |
| B10 | Backup/restore procedure tested | ⬜ | Restore from backup succeeds |

### MUST-PASS (Highly recommended, delay if not ready)

| # | Gate | Status | Verified By |
|---|------|--------|------------|
| M1 | Outbox dead letter alerting works | ⬜ | Alert received for parked event |
| M2 | Night audit failure alerting works | ⬜ | Alert received for failed audit |
| M3 | Availability query < 200ms | ⬜ | Load test |
| M4 | Booking create < 500ms | ⬜ | Load test |
| M5 | Redis degraded mode functional | ⬜ | Manual test |
| M6 | PII not in logs | ⬜ | Log grep |
| M7 | Error responses don't leak stack traces | ⬜ | Manual test |

### NICE-TO-HAVE (Can go live without)

| # | Gate | Status |
|---|------|--------|
| N1 | Collection registry (no string literals) |⬜ |
| N2 | Full pms.py decomposition | ⬜ |
| N3 | Real-time WebSocket health dashboard | ⬜ |
| N4 | Prometheus metrics endpoint | ⬜ |
| N5 | Automated nightly backup verification | ⬜ |

---

## 9. TEAM STRUCTURE RECOMMENDATION

### Minimum Team: 5 people

| Role | Person | Primary Responsibility | Days 1-7 Focus | Days 8-14 Focus |
|------|--------|----------------------|----------------|-----------------|
| **Backend Engineer 1** | Senior | Booking integrity + transactions | P0-FIX-1 (atomic booking), P0-FIX-2 (transactions), PERF-001 (indexes) | Concurrency tests, performance tuning |
| **Backend Engineer 2** | Mid-Senior | Channel manager + outbox | P0-FIX-3 (OTA→PMS bridge), P0-FIX-4 (outbox), OTA-003 (ARI persistence) | E2E OTA tests, outbox monitoring |
| **Backend Engineer 3 / DevOps** | Mid | Tenant isolation + infra | P0-FIX-5 (tenant enforcement), OBS-001 (health checks), INFRA-001 (indexes on startup) | Alerting setup, staging deployment, monitoring dashboards |
| **Frontend Engineer** | Mid | UI fixes + observability dashboards | Update calendar to show OTA bookings, outbox status dashboard, health dashboard | Testing, bug fixes, polish |
| **Founder/PM** | — | Gate owner + decision maker | Daily standup, blocker resolution, OTA vendor communication | Go/no-go decision, first hotel onboarding, rollback plan |

### What Founder/PM Must Personally Track
1. **Daily**: Are all P0 items on track? Any blockers?
2. **Day 4**: OTA → PMS bridge working in staging?
3. **Day 8**: Can we demo full booking cycle end-to-end?
4. **Day 12**: Performance numbers acceptable?
5. **Day 13**: Staging dry run successful?
6. **Day 14**: Go/No-Go decision based on gate checklist

---

## 10. FINAL CTO VERDICT

### 3 Things That Must Be Fixed First — No Debate

1. **Atomic availability check + booking create** (P0-FIX-1)
   - Without this, any concurrent booking attempt can produce a double-sell. This is the #1 revenue and trust risk. Fix it Day 1.

2. **OTA → PMS booking bridge** (P0-FIX-3)
   - The channel manager ingests OTA reservations but NEVER creates PMS bookings. This means the entire channel manager is decorative. The front desk is blind to 60-80% of reservations. Fix it by Day 4.

3. **PMS → OTA guaranteed delivery via outbox** (P0-FIX-4)
   - Every booking change is fire-and-forget to OTAs. A single dropped push means stale inventory on Booking.com/Expedia. This will cause overselling within hours of go-live. Fix it by Day 6.

### What Should Be Postponed Entirely

- **pms.py decomposition** (2714 lines): It works. It's ugly. Refactoring it now adds risk, not safety. Do it after go-live when you have test coverage.
- **Collection registry**: Nice to have. Does not affect production safety. Post go-live.
- **Frontend role-based views**: All staff see same dashboard for now. Role-based views are a feature, not a safety requirement.
- **GraphQL schema**: Nobody is using it. Remove it from scope entirely.
- **ML models, predictive engine, dynamic staffing AI**: Remove from scope. These are premature optimization.

### What Should Be Removed from Scope

- `graphql_schema.py` — No consumer
- `ml_models/`, `ml_trainers.py`, `ml_real_models.py` — Not ready for production
- `dynamic_pricing_engine.py`, `revenue_autopilot.py` — Dangerous without extensive validation
- `social_media_radar.py`, `reputation_manager.py` — Not core to PMS
- `world_class_features.py` — Title alone is a red flag
- All `create_*_demo_data.py` scripts — Should never run in production

### Fastest Safe Path to First Real Hotel Pilot

```
Week 1: Fix booking integrity (atomic + transactions + OTA bridge + outbox)
Week 2: Prove it works (tenant isolation + night audit + testing + staging dry run)
Day 14: Go-live with 1 hotel, 1 property, read-only OTA sync first
Day 21: Enable full OTA sync after 7 days of read-only monitoring
Day 30: Second hotel onboarding if first hotel stable
```

**The system has solid bones.** The ingest pipeline, lineage tracking, and domain structure show serious thought. But the last mile — actually creating bookings from OTA data and guaranteeing delivery back — is missing. Fix those two bridges and you have a viable product.

**Go-live readiness: NOT READY today. Ready in 14 days IF the war plan is executed.**

---

*End of Execution Blueprint*
*Document version: 1.0*
*Next review: Day 7 checkpoint*
