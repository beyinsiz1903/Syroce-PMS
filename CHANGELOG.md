# Hotel Operating System — Changelog

## 2026-03-12 — Phase B/C/D/F Completion: Service Wiring + Normalized Health APIs

### Service Layer Wiring (Phase B)
- **NEW** `FrontdeskService` — 13 methods covering check-in, check-out, arrivals, departures, keycards, guest alerts, audit checklist, unified views
- **NEW** `NightAuditService` — 6 methods covering audit logs, error logs, night audit logs, OTA sync logs, RMS publish logs, maintenance predictions
- **NEW** `PricingService` — 8 methods for rate plans, demand forecast, competitor rates, dynamic pricing, revenue dashboard
- **NEW** `RmsService` — 6 methods for group bookings, corporate contracts, OTA promotions, inventory, yield analysis
- **NEW** `MessagingService` — 5 methods for guest messaging, internal messaging, templates
- **NEW** `MobileOpsService` — 5 methods for no-show processing, room changes, quick tasks, mobile dashboard
- **NEW** `PosFnbService` — 9 methods for kitchen display, orders, table layout, F&B dashboard, stock management
- **UPDATED** `frontdesk_router.py` — Refactored 12+ endpoints to delegate to FrontdeskService
- **UPDATED** `night_audit_router.py` — Refactored 6 endpoints to delegate to NightAuditService
- **UPDATED** `pricing_router.py` — Wired rate update endpoint to PricingService
- **UPDATED** `messaging/router.py` — Imported MessagingService

### Schema Extraction (Phase A continued)
- **NEW** `domains/pms/pos_fnb/schemas.py` — 11 Pydantic models extracted
- **NEW** `domains/pms/mobile/schemas.py` — 7 Pydantic models extracted
- **NEW** `domains/revenue/pricing/schemas.py` — 7 Pydantic models extracted
- **NEW** `domains/revenue/rms/schemas.py` — 5 Pydantic models extracted
- **NEW** `domains/guest/messaging/schemas.py` — 6 Pydantic models extracted

### API Normalization (Phase D)
- **NEW** `routers/system_health_dashboard.py` — Role-based dashboard API `/api/system-health/role-dashboard`
- **NEW** `routers/system_health_normalized.py` — Normalized health APIs with standard contract

### Frontend Enhancement (Phase C continued)
- **UPDATED** `SystemHealthDashboard.js` — Added normalized overview bar, role context, WebSocket status, live events strip, subsystem health section

### WebSocket Infrastructure (Phase E partial)
- **UPDATED** `websocket_server.py` — Added `system-health` room, `broadcast_system_health_event()`, `broadcast_health_metric_update()`

### Testing (Phase F)
- **NEW** `tests/test_service_wiring_phase2.py` — 19 tests validating all new services, schemas, and router wiring
- **NEW** `tests/runtime/test_ota_reservation_burst.py` — OTA burst + concurrent check-in stress tests
- **NEW** `tests/runtime/test_queue_saturation.py` — Queue saturation + stuck task detection
- **NEW** `tests/runtime/test_tenant_isolation_concurrent.py` — Tenant isolation under concurrent load
- **NEW** `tests/test_system_health_normalized_api.py` — 16 API contract tests (by testing agent)
- **NEW** `load_tests/ota_reservation_burst.js` — k6 load test for OTA reservation burst
- **NEW** `load_tests/system_health_dashboard_load.js` — k6 load test for health dashboard

### Test Results
- Service wiring tests: **52 passed**
- Runtime stress tests: **6 passed**
- Testing agent: **16/16 backend + frontend all passed**

---

## 2026-03-11 — Phase A/B/C Initial: Schema Organization + Hardening Service Wiring

### Schema Organization
- Extracted ~80 inline Pydantic models to `schemas.py` files across 10+ domains

### Hardening Service Wiring
- `CMRuntimeService`, `WorkerRuntimeService`, `SecurityRuntimeService`
- Refactored hardening routers to delegate to services

### System Health Dashboard (Initial)
- Created `/system-health` page with Channel Manager, Queue/Workers, Security, Alerts panels
- Integrated with 24 hardening endpoints

### Testing
- 33 tests passed (schema organization + initial service wiring)
- Full regression by testing agent passed
