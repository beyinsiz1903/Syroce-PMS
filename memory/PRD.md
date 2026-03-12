# Syroce Hotel PMS — Product Requirements Document

## Original Problem Statement
Enterprise hotel operating system platform requiring production-hardening across backend architecture, frontend operational console, and testing frameworks. A 12-point directive covers schema organization, service wiring, role-based dashboards, WebSocket live updates, frontend stabilization, stress/load testing, API normalization, audit/observability enrichment, and comprehensive testing.

## Core Architecture
- **Backend**: FastAPI + MongoDB (Motor async) + Socket.IO
- **Frontend**: React + Shadcn/UI + Socket.IO Client
- **Pattern**: Domain-Driven Design — `router → service → repository`
- **Auth**: JWT-based, role-based access (GM, Admin, Superadmin)
- **WebSocket**: Real-time system health event broadcasting

## What's Been Implemented

### Phase 1 (Previous Sessions)
- Full domain router architecture
- Schema organization (all inline Pydantic models extracted to schemas.py files)
- Service layer creation for all domains (Frontdesk, NightAudit, PosFnb, RMS, Pricing, Messaging)
- Core service wiring for frontdesk, night_audit, pricing, messaging routers
- Common contracts: ServiceResult, OperationContext, DomainError hierarchy
- WebSocket backend infrastructure (Socket.IO rooms, broadcasting)
- Runtime stress test skeletons (tests/runtime/)
- Load test framework skeletons (load_tests/)

### Phase 2 (Current Session — Completed)
1. **CMRuntimeService Real Logic** — Replaced placeholder with real DB queries:
   - Provider health aggregation from channel_connections
   - Sync scheduler status from channel_sync_logs
   - Drift detector results from drift_scan_results
   - Reconciliation summary from reconciliation_results
   - Circuit breaker state from provider_failover
   - Health/severity calculation with evidence

2. **WorkerRuntimeService Real Logic** — Replaced placeholder with real DB queries:
   - Per-queue health breakdown (sync, notification, report, audit, import)
   - Dead letter trend and replay candidates
   - Worker heartbeat from recent task completions
   - Retry pressure metrics
   - Severity calculation with recommendations

3. **SecurityRuntimeService Real Logic** — Replaced placeholder with real DB queries:
   - Tenant guard violations from tenant_guard
   - Credential scan findings from credential_guard
   - Audit completeness score from audit_validator
   - Rate limit burst detection from rate_limiter
   - Log sanitization coverage from log_sanitizer
   - Comprehensive status aggregation

4. **Normalized Health API Enrichment** — All endpoints return enriched contract:
   - data_freshness: "real-time"
   - evidence_summary
   - degraded_reason
   - critical_blockers
   - live_capable: true
   - Endpoints: /normalized/channel-manager, /workers, /security, /observability, /alerts, /overview

5. **WebSocket Live System-Health Connection**:
   - Frontend Socket.IO client connects to backend
   - system-health room subscription
   - Live event listeners for system_health_event, health_metric_update
   - Fallback polling when WebSocket disconnected (30s interval)
   - WebSocket status badge (Live/Polling)
   - Auto-refresh on critical events

6. **Audit & Observability Enrichment**:
   - New endpoint: /api/system-health/audit/metrics
   - Drift scan duration metrics
   - Reconciliation success rate
   - Queue backlog trend
   - Security violations trend
   - Dead letter growth
   - Live status endpoint: /api/system-health/live/status

7. **Frontend Stabilization**:
   - ErrorBoundary component wrapping all routes
   - SystemHealthDashboard already lazy-loaded
   - Role-based panel visibility (GM/Admin/Superadmin)
   - WebSocket hook with reconnect strategy
   - Fallback polling abstraction
   - Severity badges, status badges, metric cards

8. **Comprehensive Hardening Tests** — 30 tests:
   - CMRuntimeService: 4 tests (real fields, sync_stats, drift, providers)
   - WorkerRuntimeService: 5 tests (queue health, per-queue, dead letter, stuck, severity)
   - SecurityRuntimeService: 5 tests (audit, rate limit, tenant guard, log sanit, severity)
   - Normalized Health Contract: 6 tests (enriched fields for all subsystems)
   - Role-Based Dashboard: 3 tests (admin panels, drift, queue)
   - Audit Metrics: 2 tests (endpoint, recon structure)
   - Live Events: 2 tests (status, events)
   - WebSocket Broadcasting: 3 tests (room, broadcast functions)

### Phase 3 (Current Session — Completed)

9. **Audit Hook Standardization**:
   - Created `common/audit_hook.py` with `@audited` decorator
   - Standardized audit fields: actor_id, actor_role, tenant_id, property_id, service_name, operation_name, target_type, target_id, result_status, severity, before_snapshot, after_snapshot, override_reason, correlation_id, duration_ms
   - `require_reason` enforcement for critical operations
   - `capture_before` for mutation before-snapshots
   - Silent failure on audit DB write errors (never breaks caller)
   - Applied to PosFnbService, MobileOpsService, RmsService, FrontdeskService

10. **API Response Normalization**:
    - Created `common/response.py` with `api_response()` and `from_service_result()`
    - Standard envelope: status, severity, message, data, correlation_id, action_available, suggested_action, last_updated_at

11. **Role-Based Dashboard Polish**:
    - GMPropertyView: property-level CM status, drift summary, property alerts, view-only panels
    - AdminTenantView: tenant cross-property, queue/worker, security, audit & observability, action buttons
    - SuperadminGlobalView: cross-tenant metrics, global subsystem health, runtime metrics, full action access
    - ScopeBanner component with role-specific icon/color/label
    - EmptyState component for clean no-data states
    - DataRow helper for consistent panel rows
    - Permission-aware CTA buttons (View Only vs actions)

12. **Stress Test Deepening**:
    - test_pos_fnb_burst.py: POS transaction burst (50), kitchen order contention, stock race, table reservation contention
    - test_mobile_concurrency.py: 20 concurrent no-shows, 5 room changes, 30 task burst, 20 issue burst
    - test_dashboard_websocket_storm.py: 200 event storm, 100 metric updates, 100 alert aggregation

13. **Comprehensive Testing**:
    - test_audit_service_wiring.py: 15 tests for audit hooks, response normalization, service wiring, scope leakage
    - All 26 new tests pass (15 audit + 11 stress)
    - Full testing agent validation: 100% backend + frontend success

### Phase 4 (Current Session — Completed)

14. **NightAuditCoreService — Real Production-Grade Logic**:
    - Business date roll with idempotency guard
    - Concurrent operation lock (MongoDB-based)
    - Room charge posting (VAT + accommodation tax per Turkish tax law)
    - No-show handling with fee posting and room release
    - Pending arrival/departure validation
    - Folio balance checking (unbalanced detection)
    - Tax consistency validation
    - Audit exception generation and persistence
    - Dry-run mode (zero DB mutations)
    - Force-rerun capability
    - Pre-audit validation (HK tasks, POS transactions, orphan check-ins, concurrent audit)

15. **Audit Timeline API Foundations**:
    - GET /api/audit/timeline — cursor-based pagination, filtering by actor/action/severity/entity
    - GET /api/audit/timeline/{entity_type}/{entity_id} — entity audit trail with before/after snapshot diffs
    - GET /api/audit/summary — aggregated audit summary by severity/operation/actor/result
    - Time-bucket grouping for timeline visualization

16. **Operational Metrics API**:
    - GET /api/metrics/operational — rooms, bookings, folios, HK, audit event counts
    - GET /api/metrics/night-audit — business date status, last run, duration trends, success rate

17. **Load Test Framework Expansion**:
    - 8 k6 scenarios: ota_reservation_burst, ari_update_storm, queue_backlog_load, night_audit_load, system_health_dashboard_load, websocket_health_stream_load, pos_fnb_burst, mobile_ops_load
    - Locust combined scenario: locust_pms.py with PMSUser + CheckoutSurge user classes
    - Each scenario: custom metrics, thresholds, multiple load profiles (normal, burst, storm)
    - README.md with failure interpretation guide

18. **Frontend Module Boundaries**:
    - 9 module index files: runtime-health, admin, frontdesk, housekeeping, finance, rms, pos_fnb, mobile, messaging
    - ModuleErrorBoundary: per-module error isolation with retry
    - useOperationalSocket hook: shared WebSocket abstraction with auto-reconnect and stale detection
    - OperationalWidgets: SeverityBadge, EmptyState, DegradedState, NetworkError components
    - AuditTimelineSummaryCard: embeddable audit summary for dashboards

19. **Observability Enrichment**:
    - Night audit duration/exception/revenue metrics
    - Business date staleness detection
    - Room/booking/folio/HK operational metrics
    - Audit event rate tracking

20. **Comprehensive Testing**:
    - test_night_audit_and_timeline.py: 14 tests (service logic, idempotency, schema, imports)
    - runtime/test_night_audit_core.py: 4 stress tests (concurrent guard, rerun safety, tenant isolation)
    - runtime/test_audit_timeline_stress.py: 3 tests (grouping, aggregation)
    - Full testing agent validation (iteration_54): 100% backend + frontend success
    - All 8 new API endpoints verified via curl

## Remaining Backlog

### P1
- Implement real business logic in remaining placeholder service methods (FrontdeskService, PosFnbService etc.)
- Expand existing k6 load test scenarios with more real-world edge cases

### P2
- Additional frontend module pages within established boundaries
- Network error recovery enhancement for all modules
- Reusable health card library extraction
- Advanced audit timeline panel UI (foundations are in place)
- Observability alerting integration (alert candidates defined)

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/system-health/normalized/overview | GET | Aggregated health across all subsystems |
| /api/system-health/normalized/channel-manager | GET | CM health with enriched contract |
| /api/system-health/normalized/workers | GET | Queue/worker health |
| /api/system-health/normalized/security | GET | Security health |
| /api/system-health/normalized/alerts | GET | Alert summary |
| /api/system-health/normalized/observability | GET | Observability health |
| /api/system-health/role-dashboard | GET | Role-scoped panel data |
| /api/system-health/audit/metrics | GET | Audit & observability metrics |
| /api/system-health/live/status | GET | WebSocket connection status |
| /api/system-health/live/events | GET | Recent system health events |
| /api/night-audit/run | POST | Execute night audit (dry_run, force_rerun supported) |
| /api/night-audit/business-date | GET | Current business date for tenant |
| /api/night-audit/history | GET | Night audit run history |
| /api/night-audit/exceptions/{id} | GET | Exceptions for a specific audit run |
| /api/audit/timeline | GET | Timeline-friendly audit log (cursor-based pagination) |
| /api/audit/timeline/{type}/{id} | GET | Entity audit trail with before/after snapshots |
| /api/audit/summary | GET | Aggregated audit summary (by severity/operation/actor) |
| /api/metrics/operational | GET | Operational metrics (rooms, bookings, folios, HK) |
| /api/metrics/night-audit | GET | Night audit metrics (trends, success rate, duration) |

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
