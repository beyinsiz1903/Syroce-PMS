# Syroce PMS — Changelog

## 2026-03-22: TI-003 Tenant Isolation Full Enforcement (P0 — Security)
- Replaced raw `db` in `core/database.py` with `TenantAwareDBProxy` that auto-scopes queries via `contextvars`
- Created `TenantContextMiddleware` that extracts `tenant_id` from JWT and sets per-request context
- 3-layer enforcement: DB Proxy (auto-injection), Runtime Guard (STRICT_TENANT_MODE), Static Audit (CI grep)
- Created `LazyCollection` descriptor for repository class-level collection access (8 repositories migrated)
- Public API: `get_db()`, `get_db_for_tenant()`, `get_system_db()`, `tenant_context()` context manager
- CI enforcement script at `scripts/check_raw_db.py` detects 264 legacy files for gradual migration
- All 260+ existing files automatically protected via proxy + middleware (zero code changes needed)
- 66 passing tests (35 unit + 31 API), 0 regressions in existing test suites

## 2026-03-22: NA-001/NA-002 Night Audit Hardening (Financial Close Engine)
- Implemented state-machine driven financial close engine (core/night_audit_hardened.py)
- Created night_audit_runs + night_audit_run_items collections with proper indexes
- Unique index on folio_charges for duplicate charge prevention
- Pipeline: validating → candidate_build → posting_charges → reconciling → rolling_date → completed
- Item-level MongoDB transactions with stale detection, resume/abort flows
- Admin API: POST /run, GET /status, GET /runs, GET /runs/{id}/items, POST /resume, POST /abort
- Enhanced /health/deep with night_audit metrics
- 44 passing tests (23 unit + 21 API)

## 2026-03-21: DATA-001 OTA → PMS Import Bridge (P0 — Automatic Booking Import)

### Core: Import Bridge Service (`core/import_bridge_service.py`)
- `auto_import_reservation_to_pms()` with atomic claim, 3-layer duplicate prevention
- Uses `create_booking_atomic` as single booking creation path (no direct inserts)
- Error classification: retryable (timeout, network, write conflict) vs permanent (mapping, validation)
- Exponential backoff: 30s → 2min → 10min → 30min → 2hr

### Core: Import Decision (`core/import_decision.py`)
- `classify_for_import()` classifies lineage records for import eligibility
- Detects: unmapped room/rate, invalid dates, cancelled status, missing guest identity

### Core: Import Retry Worker (`core/import_retry_worker.py`)
- Background async worker polling for pending/retry import records
- Stuck processing recovery (records in "processing" > 120s reset)
- Worker metrics: imported/failed/retry counts

### Admin Endpoints (`routers/import_admin.py`)
- `GET /api/imports/status` — Import bridge health + worker metrics
- `GET /api/imports/review-queue` — Paginated review queue with filters
- `GET /api/imports/events` — List imports with status/provider/tenant_id filters
- `POST /api/imports/{id}/retry` — Reset failed/review to pending
- `POST /api/imports/{id}/approve-and-import` — Approve and trigger auto-import
- `POST /api/imports/{id}/dismiss` — Dismiss review item

### Pipeline Integration
- Modified `ingest/pipeline.py`: triggers import bridge on CREATE decision
- Classifies new lineage → creates `imported_reservations` record → worker processes

### Health & Observability
- Enhanced `/health/deep` with import_bridge metrics (pending, retry, review, failed, oldest_pending_seconds, provider_failures)

### MongoDB Indexes (5 new)
- `(tenant_id, connector_id, external_reservation_id)` UNIQUE — duplicate prevention
- `(tenant_id, import_status, next_retry_at, created_at)` — worker claim
- `(tenant_id, provider, import_status, created_at)` — provider monitoring
- `(correlation_id)` — event tracing
- `bookings.(tenant_id, source.provider, source.external_reservation_id)` — source lookup

### Tests
- 22 unit tests (pytest) + 16 API tests — 38 total, all passing
- Covers: decision classification, record creation, auto-import, duplicate prevention, review required, retry scheduling, max retries, concurrent claim, admin actions, lineage linking, error classification


## 2026-03-21: OTA-002 Outbox Pattern Implementation (P0 — Guaranteed Delivery)

### Core: Outbox Service (`core/outbox_service.py`)
- `enqueue_outbox_event()` helper with transaction session support
- Idempotency key generation (tenant:event_type:entity:payload_hash)
- Error classification: retryable (timeout, 5xx, network) vs permanent (mapping, auth, schema)
- Exponential backoff: 0s → 30s → 2min → 10min → 30min
- 8 OTA event type constants (booking.created/cancelled/modified, inventory.blocked/released/updated, restriction.updated, rate.updated)

### Tests
- 17 pytest tests in `tests/test_outbox_pattern.py` — all passing

---

## 2026-03-21: Day 2-3 Implementation (BOOK-002, TI-001, PERF-001, OBS-001)

### BOOK-002: Atomic Check-in/Check-out (P0)
- Created `core/atomic_checkin_checkout.py` with `check_in_booking_atomic()` and `check_out_booking_atomic()`
- Uses MongoDB transactions (snapshot read, majority write) for full atomicity

### TI-001: Tenant Isolation Enforcement (P0)
- Created `core/tenant_db.py` with `TenantScopedDB` and `TenantScopedCollection` classes
- Auto-injects `tenant_id` into all queries on tenant-scoped collections

### PERF-001: Compound Indexes for Hot Queries
- Added 14 compound indexes in `startup.py → _ensure_performance_indexes()`

### OBS-001: Deep Health Check Endpoint
- Added `GET /health/deep` endpoint in `health_check.py`

---

## 2026-03-21: Day 1 Implementation (BOOK-001)

### BOOK-001: Atomic Booking / Overbooking Prevention (P0)
- Created `core/atomic_booking.py` with `create_booking_atomic()`
- MongoDB replica set enabled for transaction support

---

## Prior Work (Previous Sessions)
- Full PMS feature set: bookings, rooms, guests, folios, housekeeping
- Channel manager: Exely, HotelRunner integrations
- Night audit automation
- Guest journey & online check-in
- Rate management
- Reporting system
- Rate Manager Bulk Update ~6.5x Faster
