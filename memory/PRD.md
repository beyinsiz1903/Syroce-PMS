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
│   ├── common/                     # [NEW] Shared service contracts
│   │   ├── result.py               # ServiceResult, PaginatedResult
│   │   ├── errors.py               # DomainError, NotFoundError, ValidationError, etc.
│   │   └── context.py              # OperationContext (tenant/actor/property)
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
│   ├── domains/
│   │   ├── admin/
│   │   │   ├── router.py           # Admin/tenants (uses schemas.py)
│   │   │   └── schemas.py          # [NEW] Extracted admin request/response models
│   │   ├── channel_manager/
│   │   │   ├── router.py           # CM ARI + API key
│   │   │   ├── schemas.py          # [NEW] Extracted CM models
│   │   │   ├── cm_runtime_service.py # [NEW] Service layer for hardening
│   │   │   ├── hardening_router.py # Thin router → CMRuntimeService
│   │   │   ├── drift_detector.py
│   │   │   ├── reconciliation_engine.py
│   │   │   ├── sync_scheduler.py
│   │   │   ├── provider_failover.py
│   │   │   ├── encryption.py
│   │   │   └── runtime_status.py
│   │   ├── guest/
│   │   │   ├── schemas.py          # [NEW] Extracted guest models
│   │   │   └── ...
│   │   ├── pms/
│   │   │   ├── schemas.py          # [NEW] Extracted PMS models (frontdesk, mobile, etc.)
│   │   │   ├── rooms/services/room_service.py
│   │   │   ├── rooms/repositories/room_repository.py
│   │   │   ├── reservations/services/reservation_service.py
│   │   │   ├── folio/services/folio_service.py
│   │   │   ├── housekeeping/services/housekeeping_service.py
│   │   │   └── ...
│   │   ├── revenue/
│   │   │   ├── schemas.py          # [NEW] Extracted revenue models
│   │   │   └── ...
│   │   └── sales/
│   │       ├── schemas.py          # [NEW] Extracted sales models
│   │       └── ...
│   ├── workers/
│   │   ├── worker_runtime_service.py # [NEW] Service layer for hardening
│   │   ├── hardening_router.py     # Thin router → WorkerRuntimeService
│   │   ├── queue_monitor.py
│   │   ├── task_guard.py
│   │   ├── retry_strategy.py
│   │   ├── failure_archive.py
│   │   ├── celery_hooks.py
│   │   └── task_status_service.py
│   ├── security/
│   │   ├── security_runtime_service.py # [NEW] Service layer for hardening
│   │   ├── hardening_router.py     # Thin router → SecurityRuntimeService
│   │   ├── rate_limiter.py
│   │   ├── credential_guard.py
│   │   ├── log_sanitizer.py
│   │   ├── audit_validator.py
│   │   ├── tenant_guard.py
│   │   ├── property_guard.py
│   │   └── sensitive_output.py
│   ├── modules/observability/
│   │   ├── runtime_metrics.py
│   │   └── hardening_router.py
│   └── tests/
│       ├── test_service_wiring.py  # [NEW] 33 tests
│       └── test_hardening_multi_phase.py
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── SystemHealthDashboard.js # [NEW] Runtime health dashboard
│       │   └── ...
│       └── config/
│           └── navItems.js         # [UPDATED] system_health nav entry
└── memory/
    ├── PRD.md
    ├── CHANGELOG.md
    └── ROADMAP.md
```

## Completed Phases

### Phase A: Entrypoint Refactoring
- Reduced server.py from 42K to 262 lines
- Created app.py, startup.py, bootstrap modules

### Phase B: Domain Module Separation
- 751 endpoints extracted into 30 domain routers
- legacy_routes.py: 0 endpoints remaining
- Auth shadow cleanup + 23 duplicate endpoints removed

### Phase C: Channel Manager Hardening
- Runtime status aggregation, drift detection, reconciliation
- Provider circuit breaker + health monitoring
- Credential encryption at rest
- 10 new API endpoints

### Phase D: Queue & Worker Hardening
- Queue health monitoring, task idempotency
- Dead-letter archive + replay
- Retry strategy presets
- 6 new API endpoints

### Phase E: Security Hardening
- Tenant isolation guard, multi-property access guard
- Weak credential scanning, audit trail validation
- Rate limiting per-tenant, log sanitization
- 6 new API endpoints

### Phase F: Observability Wiring
- Unified runtime metrics collector
- Threshold-based alert generation
- 2 new API endpoints

### Schema Organization (2026-03-12)
- Created 6 domain schemas: admin, channel_manager, guest, pms, revenue, sales
- Extracted ~80 inline Pydantic models from router files
- Updated router imports to use centralized schemas

### Service Layer Wiring (2026-03-12)
- Created common contracts: ServiceResult, OperationContext, DomainError hierarchy
- CMRuntimeService: wraps drift, reconciliation, sync, provider, encryption
- WorkerRuntimeService: wraps queue monitor, task status, failure archive
- SecurityRuntimeService: wraps audit, rate limiting, credential guard, tenant guard
- All hardening routers refactored to thin router → service pattern
- Existing PMS services (Room, Reservation, Folio, Housekeeping) already wired

### Frontend System Health Dashboard (2026-03-12)
- New page at /system-health with live runtime data
- Panels: Channel Manager, Queue & Workers, Security Runtime, Alerts
- Metric cards: Sync Lag, Drift Count, Recon Rate, Queue Backlog, Violations
- Action buttons: Drift Scan, Run Reconciliation, Refresh
- Role-aware, dark theme, responsive design

## Backlog

### P0 — Remaining Service Wiring
- Extract inline business logic from non-hardening routers to service layer
- Target: frontdesk, night_audit, pricing, mobile, approval routers
- Create NightAuditService, PricingService, MessagingService

### P1 — Schema Completion
- Extract remaining inline models from pos_fnb_router, rms_router
- Establish clear schema validation for all endpoint inputs

### P2 — Frontend Stabilization
- Audit frontend dependencies, route-based code splitting
- Add role-based visibility (GM, Admin, Superadmin) to SystemHealthDashboard

### P3 — Operational Reliability Tests
- Runtime stress tests for OTA burst, ARI storm, queue saturation
- k6/Locust scripts for key flows

## Key Metrics
- **Total API operations**: 1,768+
- **Hardening endpoints**: 24
- **Domain routers**: 34
- **Domain schemas**: 6
- **Service classes**: 6 (Room, Reservation, Folio, Housekeeping, CMRuntime, WorkerRuntime, SecurityRuntime)
- **Test pass rate**: 33/33 (service wiring) + 24/24 (hardening regression)
- **Legacy endpoints remaining**: 0
