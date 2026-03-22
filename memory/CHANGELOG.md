# Syroce PMS — Changelog

## 2026-03-22: SEC-001 Production-Grade Secrets Management Architecture (P0 — Security)
- Implemented multi-backend secrets manager at `core/secrets/` with clean provider abstraction
- **AWS Secrets Manager backend**: boto3, adaptive retry, deterministic naming, JSON payloads, tag support
- **Local dev backend**: AES-256-GCM encrypted MongoDB store, explicitly gated non-production
- **HashiCorp Vault placeholder**: Interface + skeleton ready for future implementation
- **SecretsManager**: Unified facade with tenant/provider/property-aware CRUD, rotation, masking, health check
- **Secret naming**: `/{prefix}/{env}/channel-manager/{tenant_id}/{provider}/{property_id}`
- **Access audit**: MongoDB `secret_access_audit` collection with 90-day TTL, per-operation logging
- **Startup validation**: Fails loudly if `local_dev` used in production, missing AWS_REGION, etc.
- **Migration tooling**: `scripts/migrate_secrets.py` — dry-run, per-tenant, idempotent migration
- **Exely router refactored**: Uses SecretsManager for credential storage/retrieval (was: XOR vault)
- **HotelRunner router refactored**: Credentials now stored in SecretsManager (was: PLAINTEXT in MongoDB!)
  - `token` field removed from connection documents on new connections
  - `credentials_ref` added as opaque reference
  - Connection status endpoint excludes `token` and `credentials_ref`
- **Dual-read fallback**: `ENABLE_LEGACY_SECRET_FALLBACK=true` reads legacy stores during migration
- **46 passing tests**: 35 unit (config, naming, local/AWS/vault/manager/audit) + 11 API integration
- **Documentation**: SECRETS_ARCHITECTURE.md, SECRETS_ROLLOUT.md, SECRETS_SECURITY_CHECKLIST.md

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
- Pipeline: validating -> candidate_build -> posting_charges -> reconciling -> rolling_date -> completed
- Item-level MongoDB transactions with stale detection, resume/abort flows
- Admin API: POST /run, GET /status, GET /runs, GET /runs/{id}/items, POST /resume, POST /abort
- Enhanced /health/deep with night_audit metrics
- 44 passing tests (23 unit + 21 API)

## 2026-03-21: DATA-001 OTA -> PMS Import Bridge (P0 — Automatic Booking Import)
- `auto_import_reservation_to_pms()` with atomic claim, 3-layer duplicate prevention
- Uses `create_booking_atomic` as single booking creation path
- Error classification: retryable vs permanent
- Exponential backoff: 30s -> 2min -> 10min -> 30min -> 2hr
- Background async worker with stuck recovery
- Admin endpoints for import management
- 38 passing tests (22 unit + 16 API)

## 2026-03-21: OTA-002 Outbox Pattern Implementation (P0 — Guaranteed Delivery)
- `enqueue_outbox_event()` with transaction session support
- Idempotency key generation
- Error classification and exponential backoff
- 17 passing tests

## 2026-03-21: Day 2-3 Implementation (BOOK-002, TI-001, PERF-001, OBS-001)
- Atomic Check-in/Check-out, Tenant Isolation, Performance Indexes, Deep Health Check

## 2026-03-21: Day 1 Implementation (BOOK-001)
- Atomic Booking / Overbooking Prevention

## Prior Work (Previous Sessions)
- Full PMS feature set: bookings, rooms, guests, folios, housekeeping
- Channel manager: Exely, HotelRunner integrations
- Night audit automation, Guest journey, Online check-in
- Rate management, Reporting, Rate Manager Bulk Update
