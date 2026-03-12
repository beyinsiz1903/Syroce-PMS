# Syroce Hotel PMS — Product Requirements Document

## Original Problem Statement
Enterprise hotel operating system (42K+ line monolith) requiring production-grade refactoring:
- Entrypoint decomposition
- Domain module separation
- Channel Manager hardening
- Worker queue reliability
- Security hardening
- Runtime test suite
- Load test framework

## Architecture (Post-Refactor)

```
backend/
  server.py (262 lines)         ← Bootstrap orchestrator
  app.py (65 lines)             ← FastAPI app factory
  startup.py (216 lines)        ← Lifecycle handlers (startup/shutdown)
  legacy_routes.py (~40K lines) ← All inline endpoints (Phase B target for domain decomposition)
  
  bootstrap/
    dependency_container.py     ← DB, JWT config (single source of truth)
    middleware_registry.py      ← CORS, GZip, Security headers
    router_registry.py          ← Centralized router mounting
    worker_registry.py          ← Celery configuration
    observability_init.py       ← Logging, Sentry, Prometheus, OTel
  
  core/
    database.py                 ← MongoDB connection
    security.py                 ← Auth, JWT, password hashing
    helpers.py                  ← Tenant features, audit, module helpers
  
  domains/
    pms/
      rooms/          (services + repositories)
      reservations/   (services + repositories)
      folio/          (services + repositories)
      housekeeping/   (services + repositories)
    channel_manager/
      inventory_sync/ (services + repositories)
      sync_scheduler.py
      drift_detector.py
      reconciliation_engine.py
      provider_failover.py
    revenue/
      pricing/        (services + repositories)
    guest/
      journey/        (services + repositories)
  
  workers/
    queue_monitor.py
    task_guard.py
    retry_strategy.py
    failure_archive.py
  
  security/
    credential_guard.py
    audit_validator.py
    rate_limiter.py
    log_sanitizer.py
  
  tests/runtime/
    test_overbooking_simulation.py
    test_rate_storm.py
    test_night_audit_concurrency.py
    test_channel_drift.py
  
  routers/                      ← 26+ extracted router modules

load_tests/
  overbooking_scenario.js       (k6)
  rate_update_storm.js          (k6)
  night_audit_load.js           (k6)
  inventory_drift_simulation.js (k6)
```

## What's Been Implemented

### Phase A: Entrypoint Refactoring ✅ (2026-03-12)
- server.py reduced from 42K → 262 lines
- Bootstrap orchestrator pattern with app.py, startup.py, legacy_routes.py
- Backward compatibility preserved (all `from server import X` still works)
- 772 endpoints maintained, all routers properly mounted

### Phase B: Domain Module Separation ✅ (2026-03-12)
- PMS domain: rooms, reservations, folio, housekeeping (services + repositories)
- Channel Manager domain: inventory sync (service + repository)
- Revenue domain: pricing (service + repository)
- Guest domain: journey (service + repository)
- All domain modules are FastAPI-independent (pure business logic)

### Phase C: Channel Manager Hardening ✅ (2026-03-12)
- SyncScheduler: Periodic + event-driven inventory sync
- DriftDetector: PMS vs OTA inventory/rate comparison
- ReconciliationEngine: Auto-fix availability drifts, flag rate drifts > 10%
- ProviderFailover: Circuit breaker (CLOSED/OPEN/HALF_OPEN) + retry with exponential backoff + jitter

### Phase D: Worker & Queue Hardening ✅ (2026-03-12)
- QueueMonitor: Backlog detection, saturation alerts, stuck task detection
- TaskGuard: Idempotency with SHA-256 dedup keys + TTL
- RetryStrategy: Configurable backoff (gentle, aggressive, critical presets)
- FailureArchive: Dead letter queue with replay capability

### Phase E: Security Hardening ✅ (2026-03-12)
- CredentialGuard: Weak password detection against known weak list + patterns
- AuditValidator: Completeness validation for critical operations
- TenantRateLimiter: Token bucket per-tenant with tier-based limits
- LogSanitizer: Regex-based PII/secret redaction + secret leakage detection

### Phase F: Channel Drift Detection ✅ (2026-03-12)
- Included in Channel Manager domain (drift_detector.py)

### Phase G: Operational Reliability Tests ✅ (2026-03-12)
- test_overbooking_simulation.py: Concurrent booking race conditions
- test_rate_storm.py: High-frequency ARI update stress
- test_night_audit_concurrency.py: Audit lock contention
- test_channel_drift.py: Drift detection accuracy

### Phase H: Load Test Framework ✅ (2026-03-12)
- k6 scripts for 4 load scenarios (overbooking, rate storm, night audit, inventory drift)

### Testing Status
- Testing agent: 100% pass (19/19 backend + frontend tests)
- All 772 API endpoints operational
- Frontend dashboard fully functional

## Prioritized Backlog

### P0 (Next)
- Migrate endpoints from legacy_routes.py to domain-specific routers
- Connect domain services to existing endpoints (currently services exist alongside legacy routes)

### P1
- Wire channel manager hardening into the sync flow (sync_scheduler, drift_detector auto-start)
- Add API endpoints for security audit, drift scan, queue status
- Connect worker hardening to actual Celery tasks

### P2
- Frontend route-based code splitting
- Frontend modules restructure (frontdesk/, housekeeping/, admin/)
- Implement credential encryption at rest for channel manager
- Incident response (ops/) module

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
