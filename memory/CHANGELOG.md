# CHANGELOG

## 2026-03-12 — Schema Organization + Service Layer Wiring + Frontend Dashboard

### Common Contracts Layer
- NEW `common/result.py` — ServiceResult, PaginatedResult for standardized service returns
- NEW `common/errors.py` — DomainError hierarchy (NotFoundError, ValidationError, ConflictError, ForbiddenError, TenantViolationError)
- NEW `common/context.py` — OperationContext carrying tenant/actor/property info through service calls

### Schema Organization (Phase A)
- NEW `domains/admin/schemas.py` — 13 models extracted from admin/router.py
- NEW `domains/channel_manager/schemas.py` — 10 models extracted from CM routers
- NEW `domains/guest/schemas.py` — 11 models extracted from guest routers
- NEW `domains/revenue/schemas.py` — 12 models extracted from revenue/pricing routers
- NEW `domains/sales/schemas.py` — 8 models extracted from sales/crm_router.py
- NEW `domains/pms/schemas.py` — 20+ models extracted from PMS routers (frontdesk, mobile, notification, approvals, calendar, pos_fnb, misc)
- UPDATED `domains/admin/router.py` — imports from schemas.py
- UPDATED `domains/sales/crm_router.py` — imports from schemas.py
- UPDATED `domains/pms/frontdesk_router.py` — imports from schemas.py
- UPDATED `domains/guest/operations_router.py` — imports from schemas.py

### Service Layer Wiring (Phase B)
- NEW `domains/channel_manager/cm_runtime_service.py` — CMRuntimeService wrapping drift, recon, sync, providers, encryption
- NEW `workers/worker_runtime_service.py` — WorkerRuntimeService wrapping queue, tasks, failures, retries
- NEW `security/security_runtime_service.py` — SecurityRuntimeService wrapping audit, rate-limit, credentials, tenant-guard, log-sanitization
- REWRITTEN `domains/channel_manager/hardening_router.py` — thin router delegating to CMRuntimeService
- REWRITTEN `workers/hardening_router.py` — thin router delegating to WorkerRuntimeService
- REWRITTEN `security/hardening_router.py` — thin router delegating to SecurityRuntimeService

### Frontend: System Health Dashboard
- NEW `pages/SystemHealthDashboard.js` — runtime hardening operations dashboard
  - 4 top-level metric cards (Channel Manager, Queue Health, Alerts, Stuck Tasks)
  - Channel Manager panel (health, sync, drift, reconciliation, providers) with Drift Scan and Reconciliation actions
  - Queue & Workers panel (pending, processing, failed, saturation, stuck)
  - Security Runtime panel (audit completeness, rate limiting, tenant guard, violations, log sanitization)
  - Runtime Alerts panel (severity chips, degraded/healthy/critical states)
  - Runtime Metrics summary (sync lag, drift count, recon rate, queue backlog, violations)
  - Refresh button, last-updated timestamp
- UPDATED `App.js` — /system-health route registered
- UPDATED `config/navItems.js` — system_health navigation entry added

### Testing
- NEW `tests/test_service_wiring.py` — 33 tests covering schemas, contracts, all hardening endpoints, PMS regression
- Testing agent validation: 33/33 backend + all frontend elements verified (iteration_50)

---

## 2026-03-12 — Phase C/D/E/F: Production Runtime Hardening

### Channel Manager Hardening (Phase C)
- NEW `domains/channel_manager/hardening_router.py` — 10 runtime API endpoints
- NEW `domains/channel_manager/encryption.py` — credential encryption at rest
- NEW `domains/channel_manager/runtime_status.py` — aggregated health status
- APIs: runtime/status, drift/scan, drift/issues, reconciliation/run, reconciliation/history, sync/schedule, sync/trigger, providers/health, providers/{id}/reset, credentials/encrypt

### Worker/Queue Hardening (Phase D)
- NEW `workers/hardening_router.py` — 6 runtime API endpoints
- NEW `workers/celery_hooks.py` — pre/post task hooks for idempotency + audit
- NEW `workers/task_status_service.py` — aggregated queue/task metrics
- APIs: queues/health, tasks/stuck, tasks/{id}/unstick, tasks/failures, tasks/replay, retries/summary

### Security Hardening (Phase E)
- NEW `security/hardening_router.py` — 6 runtime API endpoints
- NEW `security/tenant_guard.py` — tenant isolation enforcement
- NEW `security/property_guard.py` — multi-property access guard
- NEW `security/sensitive_output.py` — PII/sensitive field masking
- Optimized `security/credential_guard.py` — scoped to admin roles, limited bcrypt checks
- APIs: audit/status, rate-limit/status, credentials/check, tenant-guard/status, log-sanitization/status, secret-leakage/check

### Observability Wiring (Phase F)
- NEW `modules/observability/runtime_metrics.py` — cross-subsystem metrics
- NEW `modules/observability/hardening_router.py` — 2 runtime API endpoints
- APIs: runtime/metrics, runtime/alerts

### Model Migration / Cleanup
- `legacy_routes.py` reduced from 1718 lines to 19 lines
- api_router creation moved to `server.py`

### Infrastructure
- `bootstrap/router_registry.py` updated with 4 new hardening routers (34 total)
- `app.py` updated with 4 new OpenAPI tag groups
- 24 new hardening API endpoints, all tested (24/24 passing)
