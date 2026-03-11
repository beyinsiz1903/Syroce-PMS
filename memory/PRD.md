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
   - 10 default alert rules (health drop, sync failures, stale sync, etc.)
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
   - Endpoints: GET /reliability, GET /reliability/{id}, GET /reliability/property/{id}

5. **Multi-Property Integration Dashboard**
   - Property-level aggregation
   - Tenant-wide health scoring
   - Cross-property comparison
   - Top failing/retrying properties
   - Provider distribution
   - Endpoints: GET /multi-property/dashboard|comparison|issues|health

6. **AdminControlPanel Refactor**
   - Monolithic 900-line component split into 11 lazy-loaded tab components
   - New directory: frontend/src/pages/admin/tabs/
   - Shared UI components extracted to admin/shared.js

## Test Coverage
- `/app/backend/tests/test_operational_maturity.py`: 27 tests, 100% passing
- Testing agent validation: Backend 100%, Frontend 100%

## API Endpoints Summary
All endpoints prefixed with `/api/channel-manager/v2/`
- Metrics: snapshot, history, trends, retention-cleanup, daily-aggregation
- Alerts: list, evaluate, rules CRUD, acknowledge, resolve, mute, dismiss
- Sandbox: full validation
- Reliability: all, per-connector, per-property
- Multi-Property: dashboard, comparison, issues, health
- Admin: sync-health, reconciliation, scheduler, credentials, error-queue, observability, readiness

## Backlog
- (P2) Alert notification delivery (email, SMS, webhook channels)
- (P2) Real-time WebSocket updates for admin panel
- (P3) Advanced analytics and custom report builder
- (P3) Multi-language support (i18n)
