# Syroce PMS — Product Requirements Document

## Original Problem Statement
Cloud PMS + HotelRunner Channel Manager entegrasyonu. Sistem production-grade Hotel Integration Platform haline getirilmekte.

## Core Architecture
- **Backend**: FastAPI + MongoDB (multi-tenant)
- **Frontend**: React + Shadcn/UI
- **Channel Manager v2**: Domain-driven, connector-first architecture
- **Auth**: JWT-based, RBAC for credential endpoints

## Completed Phases (All Verified & Tested)

### Production Hardening v1 (Previous Session)
- Phase 1: Sandbox Validation Service
- Phase 2: Inventory & Rate Provider Hardening (XML adapters)
- Phase 3: AES-256-GCM Credential Encryption
- Phase 4: RBAC Enforcement on credential endpoints
- Phase 5: Reconciliation Service Hardening
- Phase 6: Scheduled Inventory Sync Safety Net
- Phase 7: Event-Driven Sync Hardening
- Phase 8: Test Suite Stabilization (110/110 tests)

### Production Platform v2 (Current Session - 2026-03-11)
- **Phase 1: Admin Control Panel** — 7-tab admin dashboard:
  - Sync Health Dashboard (overall score, 24h trend chart, per-connector health)
  - Reconciliation Issues (filters, actions: retry_sync, retry_ack, revalidate_mapping, send_to_review, dismiss, bulk_dismiss)
  - Scheduler Status (stale/failed jobs, manual trigger per connector, trigger-all)
  - Credential Management (masked credentials, test/rotate/disable, RBAC enforced)
  - Error Queue (sync_failed/import_failed/ack_failed, retry/dismiss/escalate, bulk ops)
  - Observability (sync/ACK/retry rates, mapping validation, audit trail)
  - Production Readiness (9-check report, blocker detection, recommendation)
- **Phase 2: Webhook/Callback Integration** — HMAC-SHA256 verification, timestamp validation, rate limiting, domain event triggering
- **Phase 3: Connector Health Monitoring** — Per-connector metrics, 24h trend data, status aggregation
- **Phase 4: Error Queue Admin Panel** — Unified error view, single/bulk retry+dismiss+escalate
- **Phase 5: Operational Observability** — Sync/ACK/retry/mapping rates, structured audit trail
- **Phase 6: Production Readiness Validation** — 9-check report (auth, reservation pull/ACK, inventory/rate push, mapping, reconciliation, encryption, RBAC)

## Test Coverage
- 34 unit tests (test_admin_panel_phases.py) — 100% pass
- 22 API tests (test_admin_control_panel_api.py) — 100% pass
- 110 legacy tests — stable
- Testing agent: 22/22 backend + all frontend tabs verified

## Key API Endpoints
### Admin Control Panel
- `GET /api/channel-manager/v2/admin/sync-health` — Overall + per-connector health
- `GET /api/channel-manager/v2/admin/reconciliation/issues` — Filtered issue list
- `POST /api/channel-manager/v2/admin/reconciliation/issues/{id}/{action}` — Issue actions
- `GET /api/channel-manager/v2/admin/scheduler/status` — Scheduler overview
- `POST /api/channel-manager/v2/admin/scheduler/trigger/{id}` — Manual trigger
- `GET /api/channel-manager/v2/admin/credentials` — Masked credential list
- `POST /api/channel-manager/v2/admin/credentials/{id}/test|disable` — Credential ops
- `GET /api/channel-manager/v2/admin/error-queue` — Error queue + summary
- `POST /api/channel-manager/v2/admin/error-queue/retry|dismiss|escalate|bulk-retry|bulk-dismiss`
- `GET /api/channel-manager/v2/admin/observability/metrics|audit-trail`
- `POST /api/channel-manager/v2/admin/production-readiness/{id}` — Readiness check
- `GET /api/channel-manager/v2/admin/production-readiness/overview`

### Webhook
- `POST /api/channel-manager/v2/webhooks/{provider}` — Receive webhooks

## DB Collections
- `cm_connectors`, `cm_sync_jobs`, `cm_sync_events`, `cm_imported_reservations`
- `cm_channel_mappings`, `cm_reconciliation_issues`, `cm_integration_audit_log`
- `cm_credentials`, `cm_webhook_events` (NEW)

## Frontend Pages
- `/app/admin-control-panel` — Admin Control Panel (7 tabs)
- `/app/integration-hub` — Integration Hub

## Backlog / Future Work
- (P2) Webhook provider-specific parsers (e.g., HotelRunner format)
- (P2) Alerting/notification system for critical health drops
- (P3) Historical metrics retention and trend analysis
- (P3) Multi-property aggregated dashboard
