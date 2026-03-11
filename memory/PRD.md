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

- **Domain Models**: ConnectorAccount, ExternalProperty/Room/Rate, MappingRule, SyncJob/SyncEvent/PushReceipt/ChangeRecord, ReservationImportBatch/ImportedReservation, ReconciliationIssue, IntegrationAuditLog
- **Canonical Data Model**: CanonicalRoomType, CanonicalRatePlan, InventorySlice, RestrictionSet, CanonicalReservation (extended with hr_number, message_uid, requires_ack, tax_total, extras_total, daily_prices, payments, rooms, billing_address), CanonicalGuest (extended with national_id, is_citizen, billing_address), PriceBreakdown, TaxBreakdown
- **HotelRunner Connector**: REST/JSON client for reservations, XML/OTA for inventory/rates, mapper, auth, rate limiter, retry policy, typed errors
- **Application Services**: ConnectorService, MappingService, InventorySyncService, ReservationImportService, ReconciliationService, ObservabilityService
- **Infrastructure**: MongoDB repository with tenant isolation, indexes
- **API**: 30+ endpoints under /api/channel-manager/v2/
- **Frontend**: Integration Hub page at /app/integration-hub with dashboard, connector management, mapping UI, sync history, reservation imports, reconciliation, audit log

### HotelRunner Reservation Adapter - Real Provider Contract (March 2026)
**Production-grade REST/JSON adapter replacing XML stubs:**

- **REST/JSON Client**: `_request_json()` method with full error handling, audit support
- **Paginated Pull**: `GET /api/v2/apps/reservations` with per_page/page/undelivered/from_date params, MAX_PAGINATION_PAGES safety limit
- **Confirm Delivery**: `PUT /api/v2/apps/reservations/~` via message_uid per reservation
- **State Update**: `PUT /api/v2/apps/reservations/fire` for requires_response=true reservations
- **Full JSON Mapping**: reservation_id, hr_number, state, modified, requires_response, guest/firstname/lastname, address, billing_address, rooms, daily_prices, payments, total/currency/tax_total/extras_total, message_uid
- **Room Reference Extraction**: rooms[].code, inv_code, rate_code, rate_plan_code, availability_group
- **Typed Errors**: ResponseParseError, PaginationExhaustedError, AcknowledgementError
- **Raw Audit**: correlation_id per request, param masking (token/password), response truncation (4000 chars)
- **ACK Enforcement**: requires_response=true → ack_pending mandatory
- **39 Contract Tests**: Mapper, error types, model extensions, multi-room, edge cases

### Connection Test Detailed Flow (March 2026)
**Production-grade connector test with 5-step validation:**
- Backend: `test_connection_detailed()` validates auth, property access, room types, rate plans, and REST reservation API
- Response Model: Per-step status, latency_ms, error_code, message
- Audit: Each test writes `connection_tested` action to audit log
- Frontend: Dialog with loading spinner, colored per-step results, Turkish error messages

### Inventory Sync Engine (March 2026)
**Production-grade delta sync engine with full job lifecycle:**
- **SyncJob Lifecycle**: pending -> batched -> dispatched -> succeeded | retrying -> failed -> manual_review
- **Change Types**: availability_changed, stop_sell_changed, closed_to_arrival_changed, closed_to_departure_changed, minimum_stay_changed, rate_changed
- **Delta Detection**: Compares current PMS state against last-synced snapshots
- **Coalescing**: Merges consecutive changes for same room_type/rate_plan/date_range
- **Batching**: Groups coalesced updates into efficient API batches (50 per batch)
- **Rate-Limit Aware Dispatch**: Token-bucket rate limiter + retry with exponential backoff
- **Error Handling**: Retryable vs non-retryable typed errors
- **Manual Review Queue**: Jobs exceeding max retries escalated for human intervention

### Reservation Import Engine (March 2026)
**Production-grade reservation import with idempotency and full lifecycle:**
- **Idempotency Key**: connector_id + external_reservation_id + payload_fingerprint (SHA256)
- **14 Import States**: pending, matched, created, modified, cancelled, duplicate, duplicate_cancel, conflict, review, failed, acknowledged, dismissed, resolved, out_of_order
- **9 Review Reason Codes**: missing_room_mapping, missing_rate_mapping, checked_in_cancellation, modification_after_cancel, payload_conflict, unknown_room_type, amount_mismatch, date_overlap, manual_escalation
- **ACK Tracking**: ack_pending -> ack_sent | ack_failed | not_required (enforced for requires_response=true)
- **Batch Processing**: Each pull creates a ReservationImportBatch with summary counts

## Current Architecture
```
/app/backend/
├── server.py (41K lines - monolith, being refactored via Strangler Fig)
├── channel_manager/ (NEW - production-grade module)
│   ├── domain/models/ (12 entity models + canonical models)
│   ├── application/ (6 service files)
│   ├── connectors/hotelrunner/ (8 connector files)
│   ├── infrastructure/ (repository + indexes)
│   └── interfaces/ (API router)
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
- [x] HotelRunner Reservation Adapter: real REST/JSON provider contract (pull, acknowledge, state update)

### P1 - Next
- [ ] HotelRunner sandbox testing with real credentials
- [ ] Implement Mapping Engine (mapping_service.py business logic)
- [ ] CancelReservation write-path migration
- [ ] Scheduled inventory sync (cron)
- [ ] Event-driven sync (booking change -> auto push)

### P2
- [ ] Implement Reconciliation Service (reconciliation_service.py)
- [ ] Complete Admin Panel UI (Mapping screen, Error Queues)
- [ ] ChargePost write-path migration
- [ ] Credential encryption at rest
- [ ] Second connector (SiteMinder or Channex)

### P3 - Technical Debt
- [ ] Remove old ChannelManagerModule.js
- [ ] Refactor outbox worker to separate service
- [ ] server.py monolith decomposition
- [ ] Worker locking/leasing model
- [ ] Integration Hub page title low contrast fix

## Key API Endpoints

### Channel Manager v2
- `GET/POST /api/channel-manager/v2/connectors` - Connector CRUD
- `POST /api/channel-manager/v2/connectors/{id}/test` - Connection test
- `GET/POST /api/channel-manager/v2/mappings/{connector_id}` - Mapping CRUD
- `POST /api/channel-manager/v2/sync/inventory` - Push inventory (delta)
- `POST /api/channel-manager/v2/sync/rates` - Push rates (delta)
- `GET /api/channel-manager/v2/sync/jobs` - List sync jobs
- `POST /api/channel-manager/v2/reservations/pull` - Pull reservations from provider
- `GET /api/channel-manager/v2/reservations/imported` - List imported reservations
- `GET /api/channel-manager/v2/reservations/review-queue` - Manual review queue
- `GET /api/channel-manager/v2/reservations/batches` - List import batches
- `GET /api/channel-manager/v2/dashboard` - Dashboard overview
- `GET /api/channel-manager/v2/audit` - Audit log

## 3rd Party Integrations
- **HotelRunner** (Channel Manager): REST/JSON for reservations (pull + confirm delivery + state update), XML/OTA for inventory/rates, token + hr_id auth

## Testing Status
- HotelRunner Reservation Adapter: 39/39 contract tests (100%)
- Reservation Import Engine: 22/22 API tests (100%)
- Inventory Sync Engine: 9+8 tests (9 passed, 8 pre-existing rate limit errors)
- Test files:
  - /app/backend/tests/test_hr_reservation_adapter.py (NEW)
  - /app/backend/tests/test_reservation_import_engine.py
  - /app/backend/tests/test_inventory_sync_engine.py

## Mocked/Stubbed
- HotelRunner connector client: `push_availability()`, `push_rates()` use XML/OTA (functional but untested with live endpoint)
- MappingService: `get_reverse_lookup()` returns empty dict when no mappings configured
- ReconciliationService: Skeleton implementation
