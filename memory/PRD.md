# Syroce PMS - Product Requirements Document

## Product Overview
Cloud-based Property Management System (PMS) for hospitality industry. Multi-tenant SaaS architecture with modular design.

## Core Stack
- **Backend**: Python, FastAPI, MongoDB
- **Frontend**: React, TanStack Query, Axios, i18n, Recharts/Chart.js
- **Architecture**: Strangler Fig pattern, Domain-Driven Design, Event-Driven

## User Personas
| Role | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
| Front Desk | reception@hotel.com | staff123 |
| Housekeeping | housekeeping@hotel.com | staff123 |
| Finance | finance@hotel.com | staff123 |
| Sales | sales@hotel.com | staff123 |

## Core Modules
1. Reservations (CRUD + semantic migration in progress)
2. Front Desk Operations
3. Housekeeping
4. Finance / Folio Management
5. Reports / Analytics
6. Guest Messaging
7. Revenue Management
8. Loyalty
9. Marketplace
10. AI Modules
11. Security & Compliance
12. **Channel Manager v2** (NEW - HotelRunner integration)

## What's Been Implemented

### Channel Manager v2 - HotelRunner Integration (March 2026)
**Production-grade, connector-first channel manager architecture:**

- **Domain Models**: ConnectorAccount, ExternalProperty/Room/Rate, MappingRule (with ValidationStatus, invalid_reason), SyncJob/SyncEvent/PushReceipt/ChangeRecord, ReservationImportBatch/ImportedReservation, ReconciliationIssue, IntegrationAuditLog
- **Canonical Data Model**: CanonicalRoomType, CanonicalRatePlan, InventorySlice, RestrictionSet, CanonicalReservation (extended with hr_number, message_uid, requires_ack, tax_total, extras_total, daily_prices, payments, rooms, billing_address), CanonicalGuest (extended with national_id, is_citizen, billing_address), PriceBreakdown, TaxBreakdown
- **HotelRunner Connector**: REST/JSON client for reservations, XML/OTA for inventory/rates, mapper, auth, rate limiter, retry policy, typed errors
- **Application Services**: ConnectorService, MappingService (FULL), InventorySyncService, ReservationImportService, ReconciliationService, ObservabilityService
- **Infrastructure**: MongoDB repository with tenant isolation, indexes (including duplicate detection + validation status indexes)
- **API**: 33+ endpoints under /api/channel-manager/v2/
- **Frontend**: Integration Hub page at /app/integration-hub with dashboard, connector management, mapping UI, sync history, reservation imports, reconciliation, audit log

### HotelRunner Reservation Adapter - Real Provider Contract (March 2026)
**Production-grade REST/JSON adapter replacing XML stubs:**

- **REST/JSON Client**: `_request_json()` method with full error handling, audit support
- **Paginated Pull**: `GET /api/v2/apps/reservations` with per_page/page/undelivered/from_date params
- **Confirm Delivery**: `PUT /api/v2/apps/reservations/~` via message_uid per reservation
- **State Update**: `PUT /api/v2/apps/reservations/fire` for requires_response=true reservations
- **Full JSON Mapping**: reservation_id, hr_number, state, guest, rooms, pricing, message_uid
- **39 Contract Tests**: All passing

### Mapping Engine - Full Business Logic (March 2026)
**Production-grade mapping service with validation, readiness scoring, and revalidation:**

- **5 Mapping Types**: room_type, rate_plan, occupancy, meal_plan, tax_mode
- **Per-mapping Validation**: PMS entity existence (active check), external entity existence (active check), duplicate detection, tax_mode value validation
- **ValidationStatus**: pending, valid, invalid, stale - tracked per mapping
- **Sync Readiness Score (0-100)**: Weighted: 40% room coverage, 30% rate coverage, 30% validity ratio
- **Blocked Reasons**: Turkish error messages for missing/invalid mappings
- **Missing vs Invalid Classification**: Separate lists in validation report
- **Duplicate Prevention**: 409 Conflict on same PMS entity or same external entity per type
- **Revalidation Hook**: When room/rate mapping created/deleted, review-queue reservations (missing_room_mapping, missing_rate_mapping) auto-moved to pending
- **Frontend Readiness Report**: Full structured response with PMS entities, external entities, mapping groups
- **Audit Trail**: MAPPING_REVALIDATED, MAPPING_INVALIDATED, MAPPING_READINESS_CHECKED actions
- **25 Contract Tests + 17 API Tests**: All passing (42 total)

### Connection Test Detailed Flow (March 2026)
**Production-grade connector test with 5-step validation:**
- Backend: `test_connection_detailed()` validates auth, property access, room types, rate plans, and REST reservation API
- Response Model: Per-step status, latency_ms, error_code, message

### Inventory Sync Engine (March 2026)
**Production-grade delta sync engine with full job lifecycle:**
- SyncJob Lifecycle: pending -> batched -> dispatched -> succeeded | retrying -> failed -> manual_review
- Delta Detection, Coalescing, Batching, Rate-Limit Aware Dispatch

### Reservation Import Engine (March 2026)
**Production-grade reservation import with idempotency and full lifecycle:**
- Idempotency Key: connector_id + external_reservation_id + payload_fingerprint
- 14 Import States, 9 Review Reason Codes, ACK Tracking, Batch Processing

## Current Architecture
```
/app/backend/
├── server.py (monolith, being refactored via Strangler Fig)
├── channel_manager/ (production-grade module)
│   ├── domain/models/ (12 entity models + canonical models)
│   ├── application/ (6 service files - MappingService now FULL)
│   ├── connectors/hotelrunner/ (8 connector files)
│   ├── infrastructure/ (repository + indexes)
│   └── interfaces/ (API router - 33+ endpoints)
├── modules/ (semantic modules being extracted)
├── shared_kernel/ (outbox, audit, events)
├── core/ (database, security, helpers)
└── routers/
```

## Prioritized Backlog

### P0 - Completed
- [x] Channel Manager v2 architecture + HotelRunner connector
- [x] Integration Hub admin panel
- [x] Connection Test detailed flow
- [x] Inventory Sync Engine with delta sync, coalescing, lifecycle, manual review
- [x] Reservation Import Engine with idempotency, lifecycle, review queue, ACK tracking
- [x] HotelRunner Reservation Adapter: real REST/JSON provider contract
- [x] Mapping Engine: full business logic with validation, readiness score, revalidation hook

### P1 - Next
- [ ] HotelRunner sandbox testing with real credentials
- [ ] CancelReservation write-path migration
- [ ] Scheduled inventory sync (cron)
- [ ] Event-driven sync (booking change -> auto push)
- [ ] HotelRunner Connector: Live inventory/rates (replace XML stubs)

### P2
- [ ] Implement Reconciliation Service (reconciliation_service.py)
- [ ] Complete Admin Panel UI (Mapping screen components, Error Queues)
- [ ] ChargePost write-path migration
- [ ] Credential encryption at rest
- [ ] Second connector (SiteMinder or Channex)

### P3 - Technical Debt
- [ ] Remove old ChannelManagerModule.js
- [ ] Refactor outbox worker to separate service
- [ ] server.py monolith decomposition
- [ ] Worker locking/leasing model
- [ ] Integration Hub page title low contrast fix
- [ ] Fix pre-existing inventory sync test failures (8 tests in test_inventory_api.py)

## Key API Endpoints

### Channel Manager v2
- `GET/POST /api/channel-manager/v2/connectors` - Connector CRUD
- `POST /api/channel-manager/v2/connectors/{id}/test` - Connection test
- `GET/POST /api/channel-manager/v2/mappings/{connector_id}` - Mapping CRUD
- `DELETE /api/channel-manager/v2/mappings/{mapping_id}` - Delete mapping
- `POST /api/channel-manager/v2/mappings/{connector_id}/validate` - Validate all
- `POST /api/channel-manager/v2/mappings/{connector_id}/validate/{mapping_id}` - Validate single
- `GET /api/channel-manager/v2/mappings/{connector_id}/sync-readiness` - Score + blocked reasons
- `GET /api/channel-manager/v2/mappings/{connector_id}/readiness-report` - Full frontend report
- `POST /api/channel-manager/v2/sync/inventory` - Push inventory (delta)
- `POST /api/channel-manager/v2/sync/rates` - Push rates (delta)
- `GET /api/channel-manager/v2/sync/jobs` - List sync jobs
- `POST /api/channel-manager/v2/reservations/pull` - Pull reservations
- `GET /api/channel-manager/v2/reservations/imported` - List imported
- `GET /api/channel-manager/v2/reservations/review-queue` - Manual review
- `GET /api/channel-manager/v2/reservations/batches` - Import batches
- `GET /api/channel-manager/v2/dashboard` - Dashboard overview
- `GET /api/channel-manager/v2/audit` - Audit log

## 3rd Party Integrations
- **HotelRunner** (Channel Manager): REST/JSON for reservations (pull + confirm + state update), XML/OTA for inventory/rates, token + hr_id auth

## Testing Status
- HotelRunner Reservation Adapter: 39/39 contract tests (100%)
- Mapping Engine: 25/25 contract tests + 17/17 API tests (100%)
- Reservation Import Engine: 22/22 API tests (100%)
- Inventory Sync Engine: 9+8 tests (9 passed, 8 pre-existing rate limit errors)
- Test files:
  - /app/backend/tests/test_hr_reservation_adapter.py
  - /app/backend/tests/test_mapping_engine.py (25 contract tests)
  - /app/backend/tests/test_mapping_engine_api.py (17 API tests)
  - /app/backend/tests/test_reservation_import_engine.py
  - /app/backend/tests/test_inventory_sync_engine.py

## Mocked/Stubbed
- HotelRunner connector client: `push_availability()`, `push_rates()` use XML/OTA (functional but untested with live endpoint)
- ReconciliationService: Skeleton implementation
