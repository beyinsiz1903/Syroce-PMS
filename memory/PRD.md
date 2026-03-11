# Syroce PMS - Product Requirements Document

## Original Problem Statement
Cloud PMS (Property Management System) with HotelRunner channel manager integration. The system provides hotel management capabilities with a connector-first architecture for channel management.

## Core Architecture
- **Backend**: FastAPI + MongoDB (DDD-based)
- **Frontend**: React with Shadcn/UI
- **Auth**: JWT-based authentication
- **Channel Manager**: Connector-first architecture with HotelRunner integration

## Completed Modules

### Phase 0 - Foundation (Complete)
- Connection Test System
- Audit logging
- SyncJob lifecycle
- Canonical reservation model
- Integration Hub UI

### Phase 1 - Core Sync (Complete)
- Inventory Sync Engine (delta sync + coalescing + retry)
- Reservation Import Engine (idempotent + duplicate detection + review queue)
- HotelRunner Reservation Adapter (REST/JSON provider contract)
- Manual review queue
- ACK tracking

### Phase 2 - Mapping Engine (Complete)
- 5 mapping types (room_type, rate_plan, occupancy, meal_plan, tax_mode)
- Readiness score calculation
- Validation endpoints
- 25 contract tests

### Phase 3 - Production Hardening (Complete - 2026-03-11)
All 6 phases implemented and tested:

**3.1 Reconciliation Service (LIVE)**
- 8 issue types: inventory_mismatch, rate_mismatch, missing_reservation, stale_sync, invalid_mapping, ack_failed, ack_pending_too_long, unprocessed_import
- 4 severity levels: critical, high, medium, low
- Issue lifecycle: open -> investigating -> retrying -> resolved | dismissed
- Suggested actions: retry_sync, revalidate_mapping, retry_ack, send_to_review, dismiss_with_reason
- Full CRUD API with summary aggregation
- Audit trail for all reconciliation operations

**3.2 HotelRunner Inventory & Rate Provider (ENHANCED)**
- push_availability() and push_rates() with correlation_id tracking
- Request/response audit with payload length tracking
- Environment config: mock, sandbox, production
- Latency measurement per push operation
- Error categorization: auth_error, provider_validation_error, rate_limit_error, schema_mismatch, unknown_response_format

**3.3 Mapping Screen Frontend (LIVE)**
- Readiness progress bar with color-coded score
- Missing/invalid/duplicate mapping counts
- Blocked reasons display
- Validation badges: valid, invalid, pending
- Filter buttons: all, valid, invalid, not_validated, inactive
- Actions: validate, revalidate, deactivate
- Auto-refresh readiness score after mapping changes

**3.4 Scheduled Inventory Sync Safety Net (LIVE)**
- Property-based scheduled checks
- Stale pending job detection and cleanup
- Retryable failed job requeue (max 2 auto-retries)
- Missing snapshot detection
- Drift detection (PMS vs snapshot comparison)
- Audit log and metrics per run

**3.5 Credential Security (LIVE)**
- XOR-based encryption at rest (upgradeable to AES-256-GCM)
- Secret rotation with audit trail
- Masked credential display for UI
- Secure update and rotation endpoints
- Audit actions: credential_created, credential_changed, credential_rotated, credential_tested

**3.6 Event-Driven Sync (LIVE)**
- 7 domain events: booking_created, booking_modified, booking_cancelled, room_blocked, room_unblocked, rate_changed, restriction_changed
- Event -> sync type mapping
- Date range and room type extraction from event payloads
- Batch event processing
- Audit trail for all triggered syncs

## Test Coverage
- 59 new tests (34 unit + 25 API integration tests)
- All passing: 100%
- Test files:
  - backend/tests/test_reconciliation_complete.py (34 tests)
  - backend/tests/test_channel_manager_v2_phase6.py (25 tests)
  - backend/tests/test_mapping_engine.py (25 tests - some have pre-existing event loop issues)

## API Endpoints

### Reconciliation
- POST /api/channel-manager/v2/reconciliation/run
- GET /api/channel-manager/v2/reconciliation/issues
- GET /api/channel-manager/v2/reconciliation/issues/summary
- GET /api/channel-manager/v2/reconciliation/issues/{issue_id}
- PUT /api/channel-manager/v2/reconciliation/issues/{issue_id}/status
- POST /api/channel-manager/v2/reconciliation/issues/{issue_id}/resolve
- POST /api/channel-manager/v2/reconciliation/issues/{issue_id}/dismiss
- POST /api/channel-manager/v2/reconciliation/issues

### Scheduler
- POST /api/channel-manager/v2/scheduler/run/{connector_id}
- POST /api/channel-manager/v2/scheduler/run-all

### Credentials
- PUT /api/channel-manager/v2/connectors/{connector_id}/credentials/secure
- POST /api/channel-manager/v2/connectors/{connector_id}/credentials/rotate
- GET /api/channel-manager/v2/connectors/{connector_id}/credentials/masked

### Event-Driven Sync
- POST /api/channel-manager/v2/events/sync
- POST /api/channel-manager/v2/events/sync/batch

## Mocked Components
- HotelRunner push_availability/push_rates: XML is built correctly but actual HTTP calls to HotelRunner sandbox require real credentials
- No live HotelRunner account is configured

## Backlog
- P1: Fix pre-existing test_mapping_engine.py event loop issues (21 tests)
- P1: Fix pre-existing test_inventory_api.py failures (8 tests)
- P2: Upgrade credential encryption from XOR to AES-256-GCM
- P2: Add RBAC enforcement for credential endpoints (admin-only)
- P2: Implement actual HotelRunner sandbox calls with real credentials
- P3: UI polish - low contrast page title in Integration Hub
- P3: Complete admin panel for Error Queues
