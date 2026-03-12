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

### Phase 5 — Production Hardening (Current Session — Completed)

21. **FrontdeskServiceV2 — Production-Grade Front Desk**:
    - Concurrency guard via MongoDB operation locks with TTL
    - Check-in: room readiness validation, HK task check, folio auto-creation, idempotency
    - Check-out: folio balance check, force checkout (supervisor), keycard deactivation, HK task auto-creation
    - Room move: room availability check, old room release, HK task, keycard deactivation, booking history
    - Late checkout: charge posting, folio balance update, approval tracking
    - No-show processing: first night charge, room release, idempotency
    - Walk-in: guest + booking + folio + room occupation in one operation
    - Post charge: folio charge with tax calculation, idempotency
    - Void charge: supervisor-only with folio balance reversal

22. **PosFnbServiceV2 — Production-Grade POS & F&B**:
    - Order lifecycle: create with kitchen dispatch per station, close with payment, void (supervisor)
    - Duplicate posting prevention via idempotency keys
    - Stock adjustment with atomic version check (race-condition protection)
    - Table reservation with contention guard
    - Folio posting for room-charge F&B orders

23. **Alert Enrichment Engine**:
    - 15 alert rules covering: night_audit, queue, worker, channel_manager, reconciliation, websocket, messaging, security, tenant, ML
    - Severity mapping (critical/high/warning/info)
    - Cooldown/dedupe per rule
    - Blast radius assessment (property/tenant/platform)
    - Runbook hints per alert
    - MTTA/MTTR tracking on acknowledge/resolve
    - Grafana/Alertmanager/PagerDuty route compatibility

24. **Incident Response & Recovery**:
    - Incident lifecycle: create → acknowledge → resolve with timeline
    - Recovery tools: DLQ replay, stuck worker recovery, force reconciliation
    - Service health matrix (8 services with heartbeat age and incident count)
    - MTTA/MTTR measurement

25. **Channel Manager Provider Validation**:
    - Provider contract definitions (HotelRunner, Booking.com, Expedia)
    - 7-point validation suite: connection, ARI sync, reservation import, cancellation propagation, drift detection, reconciliation, rate limit
    - Sync lag measurement (p50/p95/p99/max per sync type)
    - Retryable vs non-retryable error classification per provider

26. **Tenant Isolation Hardening**:
    - Isolation validation suite: DB scope check (8 collections), cross-tenant violations, async task scope, cache/WS isolation
    - Noisy tenant detection: request ratio analysis, classification (critical/warning), recommendation
    - Resource fairness metrics: per-tenant document count and storage ratio

27. **Pilot Hotel Readiness**:
    - 17-item readiness checklist with auto/manual checks
    - Categories: channel_manager, pms, messaging, infrastructure, security, observability, performance
    - Feature toggle system: tenant-scoped, admin-only write
    - Sign-off workflow for manual verification items
    - Readiness score calculation with critical blocker identification

28. **Frontend Operational Pages**:
    - Audit Timeline Page: event timeline, severity badges, before/after diff preview, entity trail search, filters
    - Incident Dashboard Page: service health matrix, active alerts with ack/resolve, alert summary, incident list
    - Pilot Readiness Page: score ring, validation checklist, critical blockers, feature toggles

29. **Load/Chaos/Soak Test Expansion**:
    - Soak test: 6h sustained load for memory leak / reconnect leak / queue lag creep detection
    - Chaos test: provider timeout burst, concurrent frontdesk mutation, noisy tenant flood
    - Phase 5 stress test: frontdesk (100 rps), POS burst (80 rps), alert storm (20 rps)

30. **Architecture Governance**:
    - 10 Architecture Decision Records (ADR)
    - Domain dependency rules and boundaries
    - Code ownership map
    - Deprecation policy, schema versioning, endpoint lifecycle
    - Naming standards for audit operations, events, alerts, feature toggles

### Phase 6 — Runtime Validation & Go-Live Readiness (Current Session — Completed)

31. **Runtime Validation Orchestrator**:
    - 16 validation scenarios: load (5), stress (4), chaos (5), soak (2)
    - Scenario execution with threshold evaluation (p95 latency, error rate, recovery time)
    - Validation report generation with pass/fail breakdown by type
    - All load/stress/chaos scenarios pass

32. **Incident Drill Framework**:
    - 5 drill types: worker failure, provider outage, database latency, cache failure, concurrent mutation storm
    - Auto-creates incidents + alerts marked is_drill=true
    - Detection latency measurement vs expected thresholds
    - Drill cleanup API removes artifacts
    - All 5 drills execute within detection thresholds

33. **Observability Validation**:
    - 4-category validation: metrics, logs, alerts, audit timeline
    - Overall observability score: 94.1%
    - Metrics validation: API latency, queue lag, sync lag checks
    - Logs: correlation ID coverage, structured logging
    - Alerts: 15 rules, generation, cooldown, routing compatibility
    - Audit timeline: entity coverage, before/after snapshots, pagination

34. **Go-Live Readiness Scorer**:
    - 7-category weighted scoring (total=100)
    - Categories: runtime(20%), provider(15%), incident(15%), tenant(10%), observability(15%), audit(10%), pilot(15%)
    - Maturity levels: Foundation/Developing/Capable/Production Ready/Elite
    - Score persistence and history tracking
    - Current score: 91.8 (Elite), go_live_ready: true

35. **Go-Live Dashboard Frontend**:
    - Score ring with maturity badge
    - 7-category breakdown with progress bars
    - 16 validation scenarios with run buttons
    - 5 incident drill buttons
    - Validation report (72h) and drill history

## Remaining Backlog

### P1
- Run k6/Locust soak test (6-12h) in staging and collect real latency/memory metrics
- Real provider sandbox validation (HotelRunner test credentials)
- Deepen remaining PMS service logic (HousekeepingService, ReservationService production-grade)

### P2
- Populate frontend module pages (frontdesk/, housekeeping/, finance/) with operational UIs
- Full GM training view for pilot onboarding
- Canary rollout support with traffic splitting
- Tenant-specific monitoring pack per pilot hotel
- Advanced compliance export from audit timeline
- CRA → Vite migration assessment

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
| /api/frontdesk/v2/checkin | POST | Production-grade check-in with concurrency guard |
| /api/frontdesk/v2/checkout | POST | Check-out with folio balance validation |
| /api/frontdesk/v2/room-move | POST | Room move with HK task auto-creation |
| /api/frontdesk/v2/late-checkout | POST | Late checkout with charge posting |
| /api/frontdesk/v2/no-show | POST | No-show processing with first night charge |
| /api/frontdesk/v2/walk-in | POST | Walk-in booking + check-in + folio creation |
| /api/frontdesk/v2/post-charge | POST | Folio charge posting with idempotency |
| /api/frontdesk/v2/void-charge | POST | Void charge (supervisor only) |
| /api/pos/v2/orders | POST | Create POS order with kitchen dispatch |
| /api/pos/v2/orders/close | POST | Close order with payment processing |
| /api/pos/v2/orders/void | POST | Void order (supervisor only) |
| /api/pos/v2/stock/adjust | POST | Stock adjustment with race-condition protection |
| /api/pos/v2/tables/reserve | POST | Table reservation with contention guard |
| /api/alerts/rules | GET | List all 15 alert rules |
| /api/alerts/evaluate | POST | Evaluate metrics against alert rules |
| /api/alerts/active | GET | Active (unresolved) alerts |
| /api/alerts/acknowledge | POST | Acknowledge alert (calculates MTTA) |
| /api/alerts/resolve | POST | Resolve alert (calculates MTTR) |
| /api/alerts/summary | GET | Alert summary by severity/category |
| /api/incidents/create | POST | Create incident |
| /api/incidents/acknowledge | POST | Acknowledge incident |
| /api/incidents/resolve | POST | Resolve incident |
| /api/incidents/list | GET | List incidents |
| /api/incidents/service-health | GET | Service health matrix (8 services) |
| /api/incidents/recovery/replay-dlq | POST | Replay dead letter queue |
| /api/incidents/recovery/stuck-workers | POST | Recover stuck workers |
| /api/incidents/recovery/force-reconciliation | POST | Force reconciliation |
| /api/cm/validation/run | POST | Run provider validation suite |
| /api/cm/validation/providers | GET | List provider contracts |
| /api/cm/validation/sync-lag/{id} | GET | Sync lag report |
| /api/tenant-isolation/v2/validate | GET | Tenant isolation validation score |
| /api/tenant-isolation/v2/noisy-tenants | GET | Noisy tenant detection |
| /api/tenant-isolation/v2/resource-fairness | GET | Resource fairness metrics |
| /api/pilot/readiness | GET | Pilot readiness checklist + score |
| /api/pilot/sign-off | POST | Manual sign-off for readiness check |
| /api/pilot/feature-toggles | GET/POST | Feature toggle management |
| /api/validation/scenarios | GET | List all 16 validation scenarios |
| /api/validation/run | POST | Execute a validation scenario |
| /api/validation/report | GET | Validation report (pass/fail by type) |
| /api/validation/drills | GET | List 5 incident drill definitions |
| /api/validation/drills/execute | POST | Execute incident drill |
| /api/validation/drills/history | GET | Drill execution history |
| /api/validation/drills/cleanup | POST | Clean drill-generated data |
| /api/validation/observability | GET | Full observability validation (4 categories) |
| /api/validation/observability/metrics | GET | Metrics collection validation |
| /api/validation/observability/logs | GET | Log correlation validation |
| /api/validation/observability/alerts | GET | Alert system validation |
| /api/validation/observability/audit-timeline | GET | Audit timeline validation |
| /api/validation/golive-score | GET | Go-live readiness score (7 categories, maturity) |
| /api/validation/golive-score/history | GET | Historical go-live scores |

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
