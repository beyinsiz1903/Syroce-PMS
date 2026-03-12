# CHANGELOG

## 2026-03-12 — Phase C/D/E/F: Production Runtime Hardening

### Channel Manager Hardening (Phase C)
- NEW `domains/channel_manager/hardening_router.py` — 10 runtime API endpoints
- NEW `domains/channel_manager/encryption.py` — credential encryption at rest (XOR + SHA256 + salt)
- NEW `domains/channel_manager/runtime_status.py` — aggregated health across sync/drift/recon/providers
- APIs: runtime/status, drift/scan, drift/issues, reconciliation/run, reconciliation/history, sync/schedule, sync/trigger, providers/health, providers/{id}/reset, credentials/encrypt

### Worker/Queue Hardening (Phase D)
- NEW `workers/hardening_router.py` — 6 runtime API endpoints
- NEW `workers/celery_hooks.py` — pre/post task hooks for idempotency + audit
- NEW `workers/task_status_service.py` — aggregated queue/task metrics
- APIs: queues/health, tasks/stuck, tasks/{id}/unstick, tasks/failures, tasks/replay, retries/summary

### Security Hardening (Phase E)
- NEW `security/hardening_router.py` — 6 runtime API endpoints
- NEW `security/tenant_guard.py` — tenant isolation enforcement + violation tracking
- NEW `security/property_guard.py` — multi-property access guard
- NEW `security/sensitive_output.py` — PII/sensitive field masking in responses
- Optimized `security/credential_guard.py` — scoped to admin/supervisor roles, limited bcrypt checks
- APIs: audit/status, rate-limit/status, credentials/check, tenant-guard/status, log-sanitization/status, secret-leakage/check

### Observability Wiring (Phase F)
- NEW `modules/observability/runtime_metrics.py` — cross-subsystem metrics collector
- NEW `modules/observability/hardening_router.py` — 2 runtime API endpoints
- Metrics: sync lag, drift count, recon success rate, queue backlog, stuck tasks, security violations
- Alert thresholds: critical drift, queue saturation, stuck tasks, tenant violations, sync failures
- APIs: runtime/metrics, runtime/alerts

### Model Migration / Cleanup
- `legacy_routes.py` reduced from 1718 lines → 19 lines (minimal backward-compat shim)
- api_router creation moved directly to `server.py`
- ai_endpoints inclusion moved to `server.py`
- cm_push_event import updated to point directly at domain router

### Infrastructure
- `bootstrap/router_registry.py` updated with 4 new hardening routers (34 total)
- `app.py` updated with 4 new OpenAPI tag groups
- 24 new hardening API endpoints, all tested (24/24 passing)
