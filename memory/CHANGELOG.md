# CHANGELOG

## 2026-03-12 — CI/CD Lint Fix: Backend F401/F541/F841

### Lint Cleanup
- Fixed 1402 F401 (unused imports) via ruff auto-fix
- Fixed 112 F841 (unused variables) via ruff unsafe-fix
- Fixed 187 mixed lint errors in initial pass
- Added `noqa: F401` for intentional availability-check imports (try/except pattern)
- Converted `core/__init__.py` re-exports to explicit `as` aliases
- All F401, F541, F841 checks now pass

---

## 2026-03-12 — Operational Phase: Staging Soak Test Infrastructure

### Soak Test Framework
- NEW `load_tests/soak_test_staging.py` — 6-senaryo Locust soak test (OTA burst, ARI storm, dashboard polling, night audit, housekeeping, production ops)
- NEW `load_tests/soak_monitor.py` — Sistem metrik toplayici (bellek, gecikme, endpoint probelari, anomali tespiti)
- NEW `load_tests/run_soak_test.sh` — Orkestrasyon scripti (monitor + locust + rapor)
- Custom `SoakTestShape` — Ramp-up + surekli yuk + periyodik mikro-patlama
- 6 kullanici profili: FrontdeskOperator, ARIStormUser, DashboardPoller, NightAuditRunner, HousekeepingStaff, ProductionOpsMonitor

### Backend (Soak Test API)
- NEW `GET /api/production/soak-test/status` — Soak test durumu ve sonuclari
- NEW `POST /api/production/soak-test/start` — Soak testi arka planda baslat
- NEW `POST /api/production/soak-test/stop` — Calisan testi durdur
- UPDATED `ops/production_rollout_router.py` — Soak test endpoint'leri eklendi

### Frontend
- NEW `pages/SoakTestDashboard.jsx` — Canli soak test dashboard (kontroller, metrikler, trend grafikleri, endpoint probelari, Locust istatistikleri)
- UPDATED `App.js` — `/soak-test` route eklendi

### Test Sonuclari (5dk Soak Test)
- 990 istek, 0 hata (%0.00)
- p50: 6ms, p95: 14ms, p99: 17ms
- Bellek stabil (562MB backend, 96MB MongoDB)
- Verdict: **PASS**

---

## 2026-03-12 — Phase 7: Production Rollout & Pilot Readiness

### Backend Services (7 new services, 25 new API endpoints)
- NEW `ops/production_env_service.py` — 4-category environment validation (infrastructure, security, data_safety, observability), 19 checks
- NEW `ops/canary_deployment_service.py` — 4-stage canary deployment, 7 rollback triggers, stage advancement/rollback
- NEW `ops/pilot_onboarding_service.py` — 15-step onboarding lifecycle (setup, provider, operational), auto-validation, 6 success criteria
- NEW `ops/pilot_monitoring_service.py` — Tenant-specific monitoring, 8 operational alerts, daily report generation
- NEW `ops/production_load_validation_service.py` — 5 load scenarios (OTA burst, ARI storm, queue backlog, night audit, websocket)
- NEW `ops/tenant_isolation_confirmation_service.py` — 8 isolation tests (5 critical), cross-collection data leakage check
- NEW `ops/post_launch_monitoring_service.py` — 6 continuous monitors, 3 scheduled drills, maturity reporting
- NEW `ops/production_rollout_router.py` — Unified router for all Phase 7 endpoints

### Frontend
- NEW `pages/ProductionRolloutPage.js` — 8-tab dashboard (Overview, Environment, Canary Deploy, Pilot Onboarding, Monitoring, Load Validation, Tenant Isolation, Post-Launch)
- UPDATED `App.js` — /production-rollout route registered

### Testing
- NEW `tests/test_phase7_production_rollout.py` — 26 tests covering all Phase 7 services and endpoints
- Testing agent validation: 100% backend + frontend (iteration_57)

### Infrastructure
- UPDATED `bootstrap/router_registry.py` — Phase 7 router registered

---

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
