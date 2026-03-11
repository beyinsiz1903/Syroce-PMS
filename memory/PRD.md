# Syroce PMS — Product Requirements Document

## Original Problem Statement
Cloud-native Property Management System (PMS) with HotelRunner Channel Manager v2 integration. The system manages hotel operations including bookings, guests, rooms, housekeeping, and channel distribution through HotelRunner.

## Core Architecture
- **Backend**: FastAPI (Python 3.11) + MongoDB
- **Frontend**: React + Tailwind CSS + shadcn/ui
- **Channel Manager**: Connector-first architecture under `/backend/channel_manager/`

## User Persona
- **Primary**: Hotel operators (admin role) managing property operations and channel distribution
- **Auth**: JWT-based, demo account: `demo@hotel.com` / `demo123`

---

## Completed Features

### Base System (Pre-Production Hardening)
- Connection Test System
- Inventory Sync Engine (delta sync + coalescing + retry)
- Reservation Import Engine (idempotency + duplicate detection + review queue)
- HotelRunner Reservation Adapter (REST/JSON provider contract)
- Mapping Engine (5 mapping types + readiness score)
- Integration Hub UI
- Audit logging, SyncJob lifecycle, Manual review queue
- ACK tracking, Canonical reservation model

### Production Hardening — Session 1 (Completed)
- Reconciliation Service (basic)
- Live HotelRunner Inventory/Rate Provider
- Mapping Screen Frontend
- Scheduled Inventory Sync Safety Net (basic)
- Credential Vault (XOR encryption)
- Event-Driven Sync (basic)

### Production Hardening — Session 2 (Completed 2026-03-11)

**Phase 1: HotelRunner Sandbox Validation**
- `SandboxValidationService` with 10 structured checks
- Integration Readiness Report (passed/failed/blockers/recommendation)
- Endpoint: `POST /api/channel-manager/v2/sandbox/validate/{connector_id}`

**Phase 2: Inventory & Rate Provider Hardening**
- `InventoryProviderAdapter` + `RateProviderAdapter`
- Request correlation_id, raw payload audit, error categorization
- Auto-creates reconciliation issues on push failure
- Endpoints: `POST /api/channel-manager/v2/providers/inventory/push`, `/rates/push`

**Phase 3: Credential Security Hardening**
- AES-256-GCM encryption (replaced XOR)
- Secure random 12-byte IV, authentication tag, tamper detection
- Legacy XOR → AES migration support
- `EncryptionService`, `KeyManagementService`
- Endpoints: `/credentials/secure`, `/credentials/rotate`, `/credentials/migrate`

**Phase 4: RBAC Enforcement**
- Role-based access control for credential endpoints
- Allowed: `tenant_owner`, `system_admin`, `integration_admin`, `admin`
- Restricted: `operator` (read-only), `staff`, `viewer` (no access)
- Unauthorized attempts audited
- Module: `channel_manager/infrastructure/rbac.py`

**Phase 5: Reconciliation Health Score**
- Health score aggregation (0-100) based on issue severity, sync staleness, failure ratio
- Status classification: healthy/degraded/critical
- Endpoint: `GET /api/channel-manager/v2/reconciliation/health/{connector_id}`

**Phase 6: Scheduler Metrics Enhancement**
- Structured metrics in scheduler response (stale_jobs, requeued_jobs, missing_snapshots, drift_detected)
- Dashboard-ready health data

**Phase 7: Event-Driven Sync Hardening**
- Failure audit logging with `EVENT_SYNC_FAILED` action
- Auto-creates reconciliation issues for persistent failures
- Supported events: booking_created, booking_modified, booking_cancelled, room_blocked, room_unblocked, rate_changed, restriction_changed

**Phase 8: Test Suite Stabilization**
- Fixed event loop contamination between test files
- Full patching of database-dependent methods in mock tests
- **110+ tests passing, 0 failures, CI-compatible**
- UI low-contrast fix for Integration Hub page title

---

## API Endpoints Summary

### Channel Manager v2 — New Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/channel-manager/v2/sandbox/validate/{id}` | Sandbox validation (10 checks) |
| POST | `/api/channel-manager/v2/providers/inventory/push` | Inventory push via adapter |
| POST | `/api/channel-manager/v2/providers/rates/push` | Rate push via adapter |
| PUT | `/api/channel-manager/v2/connectors/{id}/credentials/secure` | AES-256-GCM credential update |
| POST | `/api/channel-manager/v2/connectors/{id}/credentials/rotate` | Credential rotation |
| GET | `/api/channel-manager/v2/connectors/{id}/credentials/masked` | Masked credential view |
| POST | `/api/channel-manager/v2/connectors/{id}/credentials/migrate` | XOR→AES migration |
| GET | `/api/channel-manager/v2/reconciliation/health/{id}` | Health score (0-100) |

---

## Test Coverage
- `test_mapping_engine.py`: 25 tests
- `test_production_hardening_v2.py`: 26 tests
- `test_production_hardening_v3.py`: 33 tests (testing agent)
- `test_reconciliation_complete.py`: 34 tests
- `test_channel_manager_v2_phase6.py`: 25 tests
- **Total: 143+ tests, all passing**

---

## Backlog

### P1 — High Priority
- Admin Panel UI for Reconciliation Issues, Scheduler Status, Credential Management
- Webhook/callback integration for real-time HotelRunner notifications

### P2 — Medium Priority
- Rate limiter dashboard and alerting
- Connector health monitoring UI widget
- Bulk credential rotation for multi-property deployments

### P3 — Low Priority
- Error Queues admin panel
- Historical sync analytics dashboard
- Export reconciliation reports (CSV/PDF)

---

## Key Collections (MongoDB)
- `cm_connectors`: Channel connectors with encrypted credentials
- `cm_sync_jobs`: Sync job lifecycle tracking
- `cm_mappings`: Entity mappings (room_type, rate_plan, etc.)
- `cm_imported_reservations`: Imported reservation records
- `cm_reconciliation_issues`: Reconciliation issue tracking
- `cm_integration_audit_log`: Full audit trail
