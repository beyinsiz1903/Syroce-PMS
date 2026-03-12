# Syroce PMS — Product Requirements Document

## Original Problem Statement
Cloud PMS + Channel Manager entegrasyon platformu. HotelRunner provider ile connector-first mimari üzerinden entegrasyon. Sistem production-grade olacak şekilde tasarlanmış olup, gerçek provider doğrulaması ve operasyonel olgunluk katmanları içerir.

## Core Architecture
- **Backend**: FastAPI + MongoDB (Motor async driver)
- **Frontend**: React + Shadcn/UI + TailwindCSS
- **Channel Manager**: Connector-first architecture with DDD patterns
- **Security**: AES-256-GCM credential encryption, RBAC, JWT auth

## Completed Features

### Phase 1 - Core PMS (Completed)
- Multi-tenant architecture with RBAC
- Room, booking, guest, folio management
- Dashboard with analytics
- Housekeeping and task management

### Phase 2 - Channel Manager v2 (Completed)
- Connector-first architecture (create/activate/pause/disable)
- HotelRunner provider integration (OTA XML)
- Inventory sync engine (delta sync, coalescing, batching)
- Reservation import engine (idempotency, duplicate protection, manual review)
- Mapping engine (room types, rate plans, validation)
- Credential security (AES-256-GCM encryption)
- Full audit trail

### Phase 3 - Operational Maturity (Completed)
- Historical metrics storage & aggregation
- Alerting engine with rules
- Reliability monitoring
- Connector health dashboard
- Background worker scheduler (APScheduler)
- Alert delivery channels (email, webhook, Slack, Teams)
- Production readiness checklist
- Admin operational dashboard (19 tabs)

### Phase 4 - Production Integration Readiness (Completed - 2026-03-12)
1. **Mapping Completeness Validation**: Room type, rate plan, occupancy, tax mode, meal plan mapping checks. Sync/import gating. Admin readiness score display.
2. **Rate Push Success Tracking**: Success/failure/retry metrics. Failure classification (auth_error, timeout, rate_limited, validation_error, provider_unavailable, provider_rejected). Integrated into health score.
3. **Connector Health Trend Analytics**: Daily/weekly trend snapshots. Period comparison with delta calculation. Time-series charts in admin dashboard.
4. **WebSocket Real-Time Admin Updates**: Live event broadcasting (alert_triggered, connector_health_change, sync_job_update, reservation_import_batch_update, scheduler_job_state_change). Auto-reconnect. Ping/pong keep-alive.
5. **Enhanced Production Readiness**: 12-point checklist including rate push and mapping completeness. 3-tier recommendation (NOT_READY / CONDITIONALLY_READY / PRODUCTION_READY).
6. **Comprehensive Testing**: 84 unit tests + 15 API tests. 100% pass rate.

## Current Admin Panel Tabs (19 total)
1. Sync Health
2. Health Dashboard
3. Health Trends (NEW)
4. Mapping Readiness (NEW)
5. Rate Push (NEW)
6. Reservations
7. Alerts
8. Alert Delivery
9. Reliability
10. Reconciliation
11. Scheduler
12. Import Jobs
13. Background Worker
14. Credentials
15. Error Queue
16. Observability
17. Readiness
18. Sandbox Validation
19. Multi-Property

## API Endpoints (New in Phase 4)
- `GET /api/channel-manager/v2/mapping-completeness/{connector_id}`
- `GET /api/channel-manager/v2/mapping-completeness/{connector_id}/sync-gate`
- `GET /api/channel-manager/v2/mapping-completeness/{connector_id}/import-gate`
- `GET /api/channel-manager/v2/rate-push-metrics/{connector_id}`
- `GET /api/channel-manager/v2/health-trend/{connector_id}/daily`
- `GET /api/channel-manager/v2/health-trend/{connector_id}/weekly`
- `GET /api/channel-manager/v2/health-trend/{connector_id}/summary`
- `WS /api/channel-manager/v2/ws/admin-updates?tenant_id=X`

## Data Models (New)
- `cm_rate_push_metrics`: Rate push operation records
- `cm_health_snapshots`: Time-series health score snapshots

## Test Coverage
- `/app/backend/tests/test_production_hardening.py` - 42 tests
- `/app/backend/tests/test_v2_integration.py` - 42 tests
- `/app/backend/tests/test_v2_new_endpoints_api.py` - 15 API tests
- Test reports: `/app/test_reports/iteration_31.json`

## Backlog
- **(P1)** Real HotelRunner sandbox end-to-end lifecycle validation with live API
- **(P1)** Enhanced UI/UX with historical trend graphs and advanced data visualizations
- **(P2)** Additional alert delivery channels (PagerDuty, SMS gateway)
- **(P2)** SLA tracking and compliance reporting based on health trends
- **(P3)** Multi-provider support beyond HotelRunner

## Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
