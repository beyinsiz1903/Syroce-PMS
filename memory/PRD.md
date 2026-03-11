# Syroce PMS — Product Requirements Document

## Original Problem Statement
Cloud-native Property Management System (PMS) with advanced HotelRunner Channel Manager integration. Multi-tenant, production-grade hospitality platform.

## Core Architecture
- **Backend**: FastAPI + MongoDB (multi-tenant)
- **Frontend**: React + Shadcn/UI + Tailwind
- **Auth**: JWT-based, RBAC
- **Channel Manager**: DDD architecture (Domain/Application/Infrastructure/Interfaces)

## Completed Modules

### Foundation (Complete)
- Connection test system
- Inventory sync engine
- Reservation import engine
- Real HotelRunner reservation adapter
- Mapping engine (entity-level, validation, auto-mapping)
- Reconciliation service
- Credential security (AES-256-GCM)
- RBAC enforcement
- Scheduled sync
- Event-driven sync architecture
- Webhook ingestion (HMAC signature verification)
- Production readiness validation

### Phase 1-6 Hotel Integration Platform (Complete — Feb 2026)
- Admin Control Panel (7-tab UI)
- Webhook/Callback Integration
- Connector Health Monitoring
- Error Queue Admin Panel
- Operational Observability
- Production Readiness Validation

### Phase 7 — Operational Maturity (Complete — Mar 11, 2026)
5 new modules implemented + AdminControlPanel refactored:

1. **Historical Metrics Storage**
   - `cm_metrics_snapshots` collection
   - Snapshot creation (hourly), daily aggregation
   - Trend calculation (24h, 7d, 30d, 90d, 1y)
   - Retention cleanup (30d hourly, 90d daily, 1y weekly)
   - Property-level and connector-level queries
   - Endpoints: POST /metrics/snapshot, GET /metrics/history, GET /metrics/trends

2. **Alerting System**
   - `cm_alerts` and `cm_alert_rules` collections
   - 12 default alert rules (health drop, sync failures, stale sync, import_failure_spike, etc.)
   - Alert evaluation engine
   - Actions: acknowledge, resolve, mute, dismiss
   - Severity: info, warning, critical
   - Endpoints: GET/POST /alerts, GET/POST /alerts/rules, POST /alerts/{id}/acknowledge|resolve|mute|dismiss

3. **Enhanced Sandbox Validation**
   - Extended 12-step validation process
   - Mapping readiness dependency validation
   - Connector health impact assessment
   - Required next actions generation
   - Endpoint: POST /sandbox/validate/{id}/full

4. **Connector Reliability Monitoring**
   - MTBF, MTTR, uptime calculation
   - Failure pattern detection (consecutive, time-window, repeated errors)
   - Connector classification (stable, healthy, degraded, unstable)
   - Import success rate factored into classification (60% sync + 40% import weight)
   - Endpoints: GET /reliability, GET /reliability/{id}, GET /reliability/property/{id}

5. **Multi-Property Integration Dashboard**
   - Property-level aggregation
   - Tenant-wide health scoring
   - Cross-property comparison
   - Import health card per property (import_total, import_failed, import_review, import_success_rate)
   - Top failing/retrying properties
   - Provider distribution
   - Endpoints: GET /multi-property/dashboard|comparison|issues|health

6. **AdminControlPanel Refactor**
   - Monolithic component split into 12 lazy-loaded tab components
   - New directory: frontend/src/pages/admin/tabs/
   - Shared UI components extracted to admin/shared.js

### Phase 8 — Reservation Import Engine Production Hardening (Complete — Mar 11, 2026)

**Core Workflow:**
- HotelRunner reservation pull with batch processing
- Per-batch summary with detailed counts (new, modified, cancelled, duplicate, conflict, review, failed, out_of_order)
- Full processing lifecycle (pending → created/modified/cancelled/review/failed)

**Idempotency & Duplicate Protection:**
- Idempotency key: connector_id + external_reservation_id + payload_fingerprint
- SHA-256 fingerprint on key fields (dates, room, rate, amount, status, email, requests)
- Duplicate detection → duplicate status
- Different payload with same external_id → modification or conflict

**Supported States:**
- new reservation → created
- duplicate reservation → duplicate
- modification → modified (PMS booking updated)
- cancellation → cancelled (PMS booking cancelled)
- out_of_order event → out_of_order (review queue)
- re-import after partial failure → reprocess from review queue

**Cancellation / Modification Rules:**
- checked-in stay cancellation → manual review (CHECKED_IN_CANCELLATION)
- missing mapping → manual review (MISSING_ROOM_MAPPING)
- already_cancelled → duplicate_cancel
- modification after cancellation → conflict (MODIFICATION_AFTER_CANCEL)
- older payload doesn't overwrite newer state (fingerprint check)

**Manual Review Queue:**
- review_reason_code (9 codes: missing_room_mapping, checked_in_cancellation, modification_after_cancel, etc.)
- severity via import_status
- suggested_action per review reason
- resolution_status tracking (reviewed_by, reviewed_at)
- reprocess action (creates PMS booking or processes cancel)
- dismiss action (marks as dismissed)
- Full audit trail for all review actions

**ACK / Notification State Tracking:**
- ack_pending → ack_sent | ack_failed | ack_retrying
- audit log entry per ACK attempt
- Failed ACKs visible in alerting system (ack_failure_spike trigger)
- Retry failed ACKs endpoint: POST /reservations/retry-acks

**Operational Maturity Integration:**
- Historical metrics: import_total, import_created, import_modified, import_cancelled, import_failed, import_review, import_duplicate, import_success_rate written to snapshots
- Alerting: import_failure_spike trigger (warning at 5, critical at 10)
- Reliability: import_success_rate factored into connector classification
- Multi-property: import health card per property (import_total, import_failed, import_review, import_success_rate)

**Data Models:**
- ImportedReservation (35+ fields, idempotency, ACK tracking, review metadata)
- ReservationImportBatch (batch-level summary with 12 count fields)
- ReconciliationIssue (existing)
- IntegrationAuditLog (40+ action types including all reservation lifecycle events)
- Indexes: (tenant_id, connector_id, external_reservation_id) unique, (tenant_id, import_status), (tenant_id, ack_status), (batch_id)

**API Endpoints:**
- POST /reservations/pull — trigger import
- GET /reservations/imported — list with filters
- GET /reservations/imported/{id} — detail
- GET /reservations/review-queue — manual review items
- POST /reservations/review-queue/{id}/reprocess — reprocess
- POST /reservations/review-queue/{id}/dismiss — dismiss
- POST /reservations/approve — legacy compat
- GET /reservations/batches — batch list
- GET /reservations/batches/{id} — batch detail
- GET /reservations/stats — dashboard stats (by_status, by_ack, review count, success rate, recent batches)
- POST /reservations/retry-acks — retry failed ACKs
- GET /reservations/audit-trail — import audit logs

**Frontend — ReservationsTab:**
- 5 sub-sections: Overview, Reservations, Review, Batches, Audit
- Overview: 4 metric cards, import/ACK status breakdowns, recent batch cards
- Reservations: filterable table with status/ACK badges, detail dialog
- Review: action-oriented queue with reprocess/dismiss buttons
- Batches: batch summary cards with all count metrics
- Audit: chronological timeline of import events
- Reservation detail dialog with full info, review actions, error display

## Test Coverage
- `/app/backend/tests/test_reservation_import_engine.py`: 25 tests, 100% passing
- `/app/backend/tests/test_reservation_import_api.py`: 15 API tests, 100% passing
- `/app/backend/tests/test_operational_maturity.py`: 27 tests, 100% passing
- Testing agent validation: Backend 100%, Frontend 100%

## API Endpoints Summary
All endpoints prefixed with `/api/channel-manager/v2/`
- Metrics: snapshot, history, trends, retention-cleanup, daily-aggregation
- Alerts: list, evaluate, rules CRUD, acknowledge, resolve, mute, dismiss
- Sandbox: full validation
- Reliability: all, per-connector, per-property
- Multi-Property: dashboard, comparison, issues, health
- Reservations: pull, imported, imported/{id}, review-queue, reprocess, dismiss, approve, batches, batches/{id}, stats, retry-acks, audit-trail
- Admin: sync-health, reconciliation, scheduler, credentials, error-queue, observability, readiness

## Backlog
- (P1) Backend Router Refactoring — split router.py into feature-based router files
- (P2) Alert notification delivery (email, SMS, webhook channels)
- (P2) Real-time WebSocket updates for admin panel
- (P3) Advanced analytics and custom report builder
- (P3) Multi-language support (i18n)
