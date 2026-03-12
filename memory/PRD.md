# Syroce Hotel PMS — Product Requirements Document

## Original Problem Statement
Enterprise hotel operating system platform refactoring and hardening for production-readiness.
Multi-phase plan to deconstruct a monolithic backend into a domain-driven architecture.

## Architecture

```
/app
├── backend/
│   ├── app.py                      # FastAPI app instance + OpenAPI tag config
│   ├── server.py                   # Thin entrypoint orchestrator (~270 lines)
│   ├── startup.py                  # Startup/shutdown event handlers
│   ├── legacy_routes.py            # DEPRECATED — minimal shim (19 lines, 0 endpoints)
│   ├── core/
│   │   ├── audit.py                # Shared audit event logger
│   │   ├── cache.py                # Shared cache decorator
│   │   ├── database.py             # MongoDB connection
│   │   ├── security.py             # Auth & JWT
│   │   ├── helpers.py              # Shared utilities
│   │   └── utils.py                # Excel, file utilities
│   ├── bootstrap/
│   │   ├── router_registry.py      # Registers all 34 domain routers
│   │   ├── dependency_container.py
│   │   └── middleware_registry.py
│   ├── domains/                    # DOMAIN ROUTERS
│   │   ├── ai/router.py            # AI/ML, predictions (45 routes)
│   │   ├── admin/router.py         # Tenants, RBAC (42+ routes)
│   │   ├── channel_manager/
│   │   │   ├── router.py           # CM ARI + API key (5 routes)
│   │   │   ├── operations_router.py # OTA connections (18 routes)
│   │   │   ├── hardening_router.py # [NEW] Runtime status, drift, recon, providers (10 routes)
│   │   │   ├── drift_detector.py   # Drift detection engine
│   │   │   ├── reconciliation_engine.py # Auto-reconciliation
│   │   │   ├── sync_scheduler.py   # Periodic sync scheduler
│   │   │   ├── provider_failover.py # Circuit breaker + retry
│   │   │   ├── encryption.py       # [NEW] Credential encryption at rest
│   │   │   └── runtime_status.py   # [NEW] Aggregated health status
│   │   ├── guest/                   # Guest domain routers
│   │   ├── sales/                   # Sales/CRM routers
│   │   ├── pms/                     # PMS domain routers (14 files)
│   │   ├── revenue/                 # Revenue/Analytics routers
│   │   └── hr/                      # HR operations router
│   ├── workers/
│   │   ├── queue_monitor.py        # Queue health monitoring
│   │   ├── task_guard.py           # Task idempotency/dedup
│   │   ├── retry_strategy.py       # Configurable retry with backoff
│   │   ├── failure_archive.py      # Dead-letter archive
│   │   ├── celery_hooks.py         # [NEW] Pre/post task hooks
│   │   ├── task_status_service.py  # [NEW] Aggregated task metrics
│   │   └── hardening_router.py     # [NEW] Worker health APIs (6 routes)
│   ├── security/
│   │   ├── rate_limiter.py         # Token bucket per-tenant
│   │   ├── credential_guard.py     # Weak password scanner
│   │   ├── log_sanitizer.py        # PII/secret redaction
│   │   ├── audit_validator.py      # Audit completeness checker
│   │   ├── tenant_guard.py         # [NEW] Tenant isolation enforcement
│   │   ├── property_guard.py       # [NEW] Multi-property access guard
│   │   ├── sensitive_output.py     # [NEW] Output field masking
│   │   └── hardening_router.py     # [NEW] Security health APIs (6 routes)
│   ├── modules/observability/
│   │   ├── runtime_metrics.py      # [NEW] Cross-subsystem metrics
│   │   └── hardening_router.py     # [NEW] Metrics + alerts APIs (2 routes)
│   └── tests/
├── frontend/
└── load_tests/
```

## Completed Phases

### Phase A: Entrypoint Refactoring ✅
- Reduced server.py from 42K to 262 lines
- Created app.py, startup.py, bootstrap modules

### Phase B: Domain Module Separation ✅
- 751 endpoints extracted into 30 domain routers
- legacy_routes.py: 0 endpoints remaining
- Auth shadow cleanup + 23 duplicate endpoints removed
- OpenAPI tag grouping configured

### Phase C: Channel Manager Hardening ✅ (2026-03-12)
- Runtime status aggregation (sync, drift, reconciliation, providers)
- Drift detection + scan-on-demand API
- Reconciliation engine + auto-fix
- Provider circuit breaker + health monitoring
- Credential encryption at rest
- Sync schedule + event-driven trigger APIs
- 10 new API endpoints

### Phase D: Queue & Worker Hardening ✅ (2026-03-12)
- Queue health monitoring (backlog, saturation, stuck detection)
- Task idempotency via dedup key
- Dead-letter archive + replay
- Retry strategy presets (gentle, aggressive, critical)
- Pre/post task hooks for audit
- 6 new API endpoints

### Phase E: Security Hardening ✅ (2026-03-12)
- Tenant isolation guard with violation tracking
- Multi-property access guard
- Weak credential scanning (admin-prioritized)
- Audit trail completeness validation
- Rate limiting per-tenant (token bucket)
- Log sanitization verification
- Sensitive output masking
- Secret leakage detection
- 6 new API endpoints

### Phase F: Observability Wiring ✅ (2026-03-12)
- Unified runtime metrics collector (sync, drift, recon, queue, security)
- Threshold-based alert generation
- Metrics snapshot persistence
- 2 new API endpoints

### Model Migration (Partial) ✅ (2026-03-12)
- legacy_routes.py cleaned from 1718 to 19 lines
- api_router moved to server.py
- All inline models are dead code (domain routers define their own)

## Backlog

### P0 — Domain Service Wiring
- Extract inline business logic from routers to service layer
- Target: router → service → repository pattern
- Priority services: RoomService, ReservationService, FolioService

### P2 — Frontend Stabilization
- Audit frontend dependencies, route-based code splitting

### P3 — Operational Reliability Tests
- Runtime stress tests in backend/tests/runtime/

### P3 — PMS Load Test Framework
- k6/Locust scripts in load_tests/

## Key Metrics
- **Total API operations**: 1,768+
- **Hardening endpoints**: 24 new
- **Domain routers**: 34 (30 original + 4 hardening)
- **Legacy endpoints remaining**: 0
- **legacy_routes.py**: 19 lines (from 24,600 original)
- **Test pass rate**: 24/24 (hardening) + 31/31 (regression)
