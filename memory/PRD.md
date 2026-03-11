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
- **Canonical Data Model**: CanonicalRoomType, CanonicalRatePlan, InventorySlice, RestrictionSet, CanonicalReservation, CanonicalGuest, PriceBreakdown, TaxBreakdown
- **HotelRunner Connector**: HTTP client, XML builder/parser (OTA protocol), mapper, auth, rate limiter, retry policy, typed errors
- **Application Services**: ConnectorService, MappingService, InventorySyncService, ReservationImportService, ReconciliationService, ObservabilityService
- **Infrastructure**: MongoDB repository with tenant isolation, indexes
- **API**: 30+ endpoints under /api/channel-manager/v2/
- **Frontend**: Integration Hub page at /app/integration-hub with dashboard, connector management, mapping UI, sync history, reservation imports, reconciliation, audit log

### Connection Test Detailed Flow (March 2026)
**Production-grade connector test with 5-step validation:**
- Backend: `test_connection_detailed()` validates auth, property access, room types, rate plans, and XML API
- Response Model: Per-step status, latency_ms, error_code, message
- Audit: Each test writes `connection_tested` action to audit log
- Frontend: Dialog with loading spinner, colored per-step results, Turkish error messages

### Inventory Sync Engine (March 2026)
**Production-grade delta sync engine with full job lifecycle:**
- **SyncJob Lifecycle**: pending -> batched -> dispatched -> succeeded | retrying -> failed -> manual_review
- **Change Types**: availability_changed, stop_sell_changed, closed_to_arrival_changed, closed_to_departure_changed, minimum_stay_changed, rate_changed
- **Delta Detection**: Compares current PMS state (rooms, bookings, restrictions, rates) against last-synced snapshots
- **Coalescing**: Merges consecutive changes for same room_type/rate_plan/date_range into single updates
- **Batching**: Groups coalesced updates into efficient API batches (50 per batch)
- **Rate-Limit Aware Dispatch**: Token-bucket rate limiter + retry with exponential backoff
- **Error Handling**: Retryable (RateLimitError, ProviderUnavailableError) vs non-retryable (AuthenticationError, ValidationError, XmlParseError)
- **Manual Review Queue**: Jobs exceeding max retries escalated to manual_review for human intervention
- **Audit Logging**: Every lifecycle transition and dispatch attempt logged with latency
- **Separate Payloads**: Inventory (OTA_HotelAvailNotifRQ) and rates (OTA_HotelRateAmountNotifRQ) dispatched independently
- **Frontend**: Enhanced Sync Jobs tab with change type badges, delta stats, clickable job detail dialog showing lifecycle timeline, stats grid, events list, retry/dismiss actions

### Reservation Import Engine (March 2026)
**Production-grade reservation import with idempotency and full lifecycle:**
- **Idempotency Key**: connector_id + external_reservation_id + payload_fingerprint (SHA256 hash of canonical fields)
- **14 Import States**: pending, matched, created, modified, cancelled, duplicate, duplicate_cancel, conflict, review, failed, acknowledged, dismissed, resolved, out_of_order
- **9 Review Reason Codes**: missing_room_mapping, missing_rate_mapping, checked_in_cancellation, modification_after_cancel, payload_conflict, unknown_room_type, amount_mismatch, date_overlap, manual_escalation
- **ACK Tracking**: ack_pending -> ack_sent | ack_failed | not_required
- **Batch Processing**: Each pull creates a ReservationImportBatch with summary counts (new, modified, cancelled, duplicate, conflict, review, failed, out_of_order, ack_sent, ack_failed)
- **Cancellation Rules**:
  - Checked-in stay -> manual review (checked_in_cancellation)
  - Already cancelled -> duplicate_cancel
  - Modification after cancellation -> conflict (modification_after_cancel)
  - Missing mapping -> review (missing_room_mapping)
- **Manual Review Queue**: Reprocess (creates PMS booking or approves cancel) and dismiss actions
- **PMS Integration**: Creates/modifies/cancels bookings in PMS, creates guests
- **Audit Logging**: 15 reservation-specific audit actions
- **Frontend**: Enhanced Reservations tab with pull action, import batch cards, reservations table with status/ACK badges, review queue with reprocess/dismiss, reservation detail dialog, batch detail dialog
- **New Endpoints**: 9 endpoints for pull, list, detail, review queue, reprocess, dismiss, batches, batch detail, approve

### Semantic Migration (Previous Work)
- Outbox event processing system (pending -> processing -> processed/failed/parked)
- ModifyReservation write-path (PUT /api/reservations/semantic/{id})
- Migration health score (GREEN)

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
│   ├── reservations/
│   ├── stays/
│   ├── inventory/
│   └── folio/
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

### P1 - Next
- [ ] HotelRunner sandbox testing with real credentials
- [ ] CancelReservation write-path migration
- [ ] Scheduled inventory sync (cron)
- [ ] Event-driven sync (booking change -> auto push)

### P2
- [ ] ChargePost write-path migration
- [ ] Parked/failed event re-drive mechanism
- [ ] Credential encryption at rest
- [ ] Second connector (SiteMinder or Channex)

### P3 - Technical Debt
- [ ] Remove old ChannelManagerModule.js
- [ ] Refactor outbox worker to separate service
- [ ] server.py monolith decomposition
- [ ] Worker locking/leasing model

## Key API Endpoints

### Channel Manager v2
- `GET/POST /api/channel-manager/v2/connectors` - Connector CRUD
- `POST /api/channel-manager/v2/connectors/{id}/test` - Connection test
- `GET/POST /api/channel-manager/v2/mappings/{connector_id}` - Mapping CRUD
- `POST /api/channel-manager/v2/sync/inventory` - Push inventory (delta)
- `POST /api/channel-manager/v2/sync/rates` - Push rates (delta)
- `GET /api/channel-manager/v2/sync/jobs` - List sync jobs
- `GET /api/channel-manager/v2/sync/jobs/{id}` - Job detail with events
- `GET /api/channel-manager/v2/sync/jobs/{id}/events` - Job events
- `GET /api/channel-manager/v2/sync/manual-review` - Manual review queue
- `POST /api/channel-manager/v2/sync/manual-review/{id}/retry` - Retry failed job
- `POST /api/channel-manager/v2/sync/manual-review/{id}/dismiss` - Dismiss review
- `POST /api/channel-manager/v2/reservations/pull` - Pull reservations from provider
- `GET /api/channel-manager/v2/reservations/imported` - List imported reservations
- `GET /api/channel-manager/v2/reservations/imported/{id}` - Reservation detail
- `GET /api/channel-manager/v2/reservations/review-queue` - Manual review queue
- `POST /api/channel-manager/v2/reservations/review-queue/{id}/reprocess` - Reprocess review
- `POST /api/channel-manager/v2/reservations/review-queue/{id}/dismiss` - Dismiss review
- `GET /api/channel-manager/v2/reservations/batches` - List import batches
- `GET /api/channel-manager/v2/reservations/batches/{id}` - Batch detail
- `POST /api/channel-manager/v2/reservations/approve` - Approve review (backward compat)
- `GET /api/channel-manager/v2/dashboard` - Dashboard overview
- `POST /api/channel-manager/v2/reconciliation/run` - Run reconciliation
- `GET /api/channel-manager/v2/audit` - Audit log

## 3rd Party Integrations
- **HotelRunner** (Channel Manager): OTA/XML protocol, token + hr_id auth (sandbox mode)

## Testing Status
- Inventory Sync Engine: Backend 17/17 (100%), Frontend 100%
- Reservation Import Engine: Backend 22/22 (100%), Frontend 100%
- Test files: /app/backend/tests/test_inventory_sync_engine.py, /app/backend/tests/test_reservation_import_engine.py
- Test reports: /app/test_reports/iteration_21.json, /app/test_reports/iteration_22.json

## Mocked/Stubbed
- HotelRunner connector client: `pull_reservations()`, `acknowledge_reservations()`, `update_availability_and_rates()` methods are stubbed (sandbox endpoint doesn't exist)
- MappingService: `get_reverse_lookup()` returns empty dict when no mappings configured
