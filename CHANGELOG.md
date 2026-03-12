# Syroce Hotel PMS — Changelog

## [2026-03-12] Phase 6: Runtime Validation & Go-Live Readiness

### Added — Backend
- **Runtime Validation Orchestrator** (`ops/runtime_validation.py`): 16 validation scenarios across 4 types (load:5, stress:4, chaos:5, soak:2). Executes scenarios, measures p50/p95/p99 latency, error rate, recovery time. Generates validation reports with pass/fail breakdown.
- **Incident Drill Framework** (`ops/incident_drill.py`): 5 drill types — worker failure, provider outage, database latency, cache failure, concurrent mutation storm. Automatically creates incidents + alerts marked `is_drill=true`. Measures detection latency, compares against expected thresholds. Cleanup API removes drill artifacts.
- **Observability Validation** (`ops/observability_validation.py`): 4-category validation — metrics (API latency, queue lag, sync lag), logs (correlation IDs, completeness), alerts (rules, generation, routing), audit timeline (entity coverage, snapshots, pagination). Produces per-category scores.
- **Go-Live Readiness Scorer** (`ops/golive_scorer.py`): 7-category weighted scoring (runtime: 20%, provider: 15%, incident: 15%, tenant: 10%, observability: 15%, audit: 10%, pilot: 15%). Maturity levels: Foundation/Developing/Capable/Production Ready/Elite. Persists score history.
- **Validation API Router** (`ops/validation_router.py`): 13 endpoints — scenarios, run, report, drills, drills/execute, drills/history, drills/cleanup, observability (full + 4 sub-categories), golive-score, golive-score/history

### Added — Frontend
- **Go-Live Dashboard Page** (`pages/GoLiveDashboardPage.js`): Score ring with maturity badge, 7-category breakdown with progress bars, 16 validation scenarios with run buttons, 5 incident drill buttons, validation report summary (72h), drill history with pass/fail indicators

### Changed
- `bootstrap/router_registry.py` — Registered validation_router
- `App.js` — Added /golive-dashboard route

### Testing
- 19 API integration tests (`tests/test_phase6_api.py`) — 100% pass
- Full testing agent validation (iteration_56): 100% backend + frontend
- Go-Live Score: 91.8 (Elite), go_live_ready: true

---


## [2026-03-12] Phase 5: Production Hardening, Incident Response, Provider Validation & Pilot Readiness

### Added — Backend
- **FrontdeskServiceV2** (`domains/pms/frontdesk_service_v2.py`): Production-grade front desk with concurrency guard (MongoDB locks), room move, late checkout, no-show processing, walk-in booking, early checkout, folio charge posting, void charge with supervisor override. Full @audited integration.
- **Frontdesk API v2** (`domains/pms/frontdesk_router_v2.py`): 8 endpoints — checkin, checkout, room-move, late-checkout, no-show, walk-in, post-charge, void-charge
- **PosFnbServiceV2** (`domains/pms/pos_fnb/pos_fnb_service_v2.py`): Full POS lifecycle — create order with kitchen dispatch, close with payment, void order (supervisor only), stock adjustment with race-condition protection, table reservation with contention guard. Idempotency keys throughout.
- **POS API v2** (`domains/pms/pos_fnb_router_v2.py`): 5 endpoints — orders, orders/close, orders/void, stock/adjust, tables/reserve
- **Alert Enrichment Engine** (`modules/observability/alert_enrichment.py`): 15 alert rules with severity mapping, cooldown/dedupe, blast radius, runbook hints, MTTA/MTTR tracking, Grafana/Alertmanager/PagerDuty compatibility
- **Alert API** (`modules/observability/alert_router.py`): evaluate, active, acknowledge, resolve, summary, rules
- **Incident Response Service** (`modules/incident/incident_service.py`): Full incident lifecycle (create→ack→resolve), recovery tools (DLQ replay, stuck worker recovery, force reconciliation), service health matrix (8 services)
- **Incident API** (`modules/incident/incident_router.py`): create, acknowledge, resolve, list, recovery/replay-dlq, recovery/stuck-workers, recovery/force-reconciliation, service-health
- **Provider Validation Service** (`domains/channel_manager/provider_validation.py`): Provider contract definitions (HotelRunner, Booking.com, Expedia), 7-point validation suite (connection, ARI, reservation import, cancellation propagation, drift detection, reconciliation, rate limit), sync lag measurement
- **CM Validation API** (`domains/channel_manager/validation_router.py`): run, sync-lag, providers
- **Tenant Isolation Service** (`security/tenant_isolation_service.py`): Isolation validation suite (DB scope, cross-tenant violation, async task scope, cache, WebSocket room), noisy tenant detection with classification, resource fairness metrics
- **Tenant Isolation API** (`security/tenant_isolation_router.py`): validate, noisy-tenants, resource-fairness
- **Pilot Readiness Service** (`ops/pilot_readiness.py`): 17-item readiness checklist with auto/manual checks, feature toggle system, sign-off workflow, readiness score calculation
- **Pilot API** (`ops/pilot_router.py`): readiness, sign-off, feature-toggles (GET/POST)

### Added — Frontend
- **Audit Timeline Page** (`pages/AuditTimelinePage.js`): Full audit timeline with event list, severity badges, before/after diff preview, entity trail search, cursor pagination, filters (severity, entity type, actor)
- **Incident Dashboard Page** (`pages/IncidentDashboardPage.js`): Service health matrix (8 services), active alerts with acknowledge/resolve, alert summary, incident list
- **Pilot Readiness Page** (`pages/PilotReadinessPage.js`): Score ring visualization, validation checklist with severity badges, critical blockers, feature toggles with toggle UI

### Added — Load/Chaos/Soak Tests
- **Soak Test** (`load_tests/k6/scenarios/soak_test.js`): 6h sustained load for memory leak, reconnect leak, queue lag creep detection
- **Chaos Test** (`load_tests/k6/scenarios/chaos_test.js`): Provider timeout burst, concurrent frontdesk mutation, noisy tenant flood
- **Phase 5 Stress Test** (`load_tests/k6/scenarios/phase5_stress.js`): Frontdesk stress (100 rps), POS burst (80 rps), alert evaluation storm (20 rps)

### Added — Architecture Governance
- **ADR Document** (`docs/ARCHITECTURE_DECISIONS.md`): 10 Architecture Decision Records (DDD, MongoDB, JWT/RBAC, Socket.IO, Audit Hook, Concurrency Guard, Alert Rules, Provider Contracts, Feature Toggles, Incident Lifecycle)
- **Domain Rules** (`docs/DOMAIN_RULES.md`): Dependency rules, domain boundaries, shared package contracts, naming standards, deprecation policy, schema versioning, endpoint lifecycle

### Changed
- `bootstrap/router_registry.py` — Registered 7 new routers (frontdesk_v2, pos_v2, alerts, incidents, cm_validation, tenant_isolation_v2, pilot)
- `App.js` — Added routes for /audit-timeline, /pilot-readiness, /incident-dashboard

### Testing
- 24 API integration tests (`tests/test_phase5_api.py`) — 100% pass
- 26 comprehensive tests (`tests/test_phase5_comprehensive.py`) — 100% pass
- Full testing agent validation (iteration_55): 100% backend + frontend success
- 32 API endpoints verified, 3 frontend pages verified with data-testid coverage

---


## [2026-03-12] Phase 4: PMS Core Logic, Load Tests, Module Boundaries & Audit Timeline

### Added
- **NightAuditCoreService** (`domains/pms/night_audit/service.py`): Production-grade night audit engine with business date roll, room charge posting (VAT + accommodation tax), no-show handling, folio balance check, tax consistency validation, concurrent lock guard, idempotency, dry-run mode
- **Night Audit API** (`domains/pms/night_audit/router.py`): POST /run, GET /business-date, GET /history, GET /exceptions/{id}
- **Night Audit Schemas** (`domains/pms/night_audit/schemas.py`): NightAuditStatus, AuditExceptionSeverity, RunNightAuditRequest, NightAuditSummary, AuditException
- **Night Audit Validations** (`domains/pms/night_audit/validations.py`): Pre-audit checks (HK tasks, POS transactions, orphan check-ins, concurrent audit)
- **Audit Timeline API** (`routers/audit_timeline.py`): GET /timeline (cursor-based), GET /timeline/{entity}/{id} (entity trail with diffs), GET /summary (aggregation by severity/operation/actor)
- **Operational Metrics API** (`routers/operational_metrics.py`): GET /metrics/operational, GET /metrics/night-audit
- **Load Tests — k6**: ota_reservation_burst.js, ari_update_storm.js, queue_backlog_load.js, night_audit_load.js, system_health_dashboard_load.js, websocket_health_stream_load.js, pos_fnb_burst.js, mobile_ops_load.js
- **Load Tests — Locust**: locust_pms.py (PMSUser + CheckoutSurge user classes)
- **Load Test Docs**: README.md with profiles, thresholds, failure interpretation
- **Frontend Module Boundaries**: 9 module index files (runtime-health, admin, frontdesk, housekeeping, finance, rms, pos_fnb, mobile, messaging)
- **ModuleErrorBoundary**: Per-module error isolation with retry
- **useOperationalSocket**: Shared WebSocket hook with auto-reconnect and stale detection
- **OperationalWidgets**: SeverityBadge, EmptyState, DegradedState, NetworkError components
- **AuditTimelineSummaryCard**: Embeddable audit summary card for dashboards
- **Backend Tests**: test_night_audit_and_timeline.py (14), runtime/test_night_audit_core.py (4), runtime/test_audit_timeline_stress.py (3)

### Changed
- `bootstrap/router_registry.py` — Registered night_audit.router, audit_timeline, operational_metrics

### Testing
- All 21 new tests pass (14 unit + 7 runtime stress)
- Full testing agent validation (iteration_54): 100% backend + frontend success
- All 8 new API endpoints verified via curl with correct response schemas

---


## [2026-03-12] Phase 3: Service Wiring, Audit Hooks & Dashboard Polish

### Added
- **`common/audit_hook.py`**: `@audited` decorator for automatic service-level audit trail generation with standardized fields (actor_id, actor_role, tenant_id, operation_name, target_type, severity, duration_ms, before/after snapshots, correlation_id)
- **`common/response.py`**: `api_response()` and `from_service_result()` for normalized API response envelopes
- **Audit hooks on PosFnbService**: `create_pos_transaction`, `complete_kitchen_order`, `update_kitchen_order_status`, `adjust_stock`
- **Audit hooks on MobileOpsService**: `process_no_show`, `change_room`, `create_quick_task`, `create_quick_issue`
- **Audit hooks on RmsService**: `create_group_booking`, `create_corporate_contract`, `create_ota_promotion`, `record_inventory_usage`
- **Audit hooks on FrontdeskService**: `checkin`, `checkout`, `express_checkin`, `issue_keycard`, `deactivate_keycard`
- **Role-based dashboard components**: `GMPropertyView`, `AdminTenantView`, `SuperadminGlobalView`
- **UI components**: `ScopeBanner` (role icon/color/label), `EmptyState`, `DataRow`
- **Permission-aware CTAs**: GM gets View Only, Admin gets tenant actions, Superadmin gets global actions
- **Stress tests**: `test_pos_fnb_burst.py` (4 tests), `test_mobile_concurrency.py` (4 tests), `test_dashboard_websocket_storm.py` (3 tests)
- **Audit & wiring tests**: `test_audit_service_wiring.py` (15 tests: audit hooks, response normalization, service wiring, scope leakage)

### Changed
- `SystemHealthDashboard.js` — Full rewrite with 3 dedicated role-based view components
- `frontdesk_service.py` — Added @audited on 5 mutating methods
- `pos_fnb_service.py` — Added @audited on 4 mutating methods
- `mobile_ops_service.py` — Added @audited on 4 mutating methods
- `rms_service.py` — Added @audited on 4 mutating methods

### Test Results
- Backend: 26/26 new tests passed (15 audit_service_wiring + 11 runtime stress)
- Frontend: All role-based components verified by testing agent
- APIs: 6/6 health endpoints verified with correct response schemas
- Full regression: PASSED (iteration_53.json)

## [2026-03-12] Phase 2: Runtime Hardening & Live Operational Console

### Added
- **CMRuntimeService real logic**: Provider health aggregation, sync scheduler status, drift detector results, reconciliation summary, circuit breaker states, severity calculation — all from real MongoDB queries
- **WorkerRuntimeService real logic**: Per-queue health breakdown (5 queue types), dead letter trend/replay, worker heartbeat detection, retry pressure metrics, severity with recommendations
- **SecurityRuntimeService real logic**: Tenant guard violations, credential scan findings, audit completeness scoring, rate limit burst detection, log sanitization coverage testing, comprehensive status aggregation
- **Enriched Normalized Health API**: All endpoints return enriched contract with data_freshness, evidence_summary, degraded_reason, critical_blockers, live_capable fields
- **New endpoint**: `/api/system-health/audit/metrics` — drift scans, reconciliation success rate, queue backlog, security violations, dead letter growth
- **New endpoint**: `/api/system-health/live/status` — WebSocket connection count and last event
- **New endpoint**: `/api/system-health/live/events` — Recent system health events for fallback replay
- **Frontend WebSocket client**: Socket.IO connection to system-health room, live event listeners, auto-refresh on critical events, fallback polling at 30s
- **Frontend ErrorBoundary**: Wraps all routes in App.js with retry capability
- **Frontend role-based UI**: Panels conditionally rendered based on user role (GM/Admin/Superadmin)
- **Frontend Audit & Observability section**: Real-time metrics display for drift scans, recon rate, queue backlog, violations, dead letter
- **Frontend Subsystem Health section**: Normalized health cards with status, severity, evidence, degraded reason
- **30 comprehensive hardening tests**: CM runtime, worker runtime, security runtime, normalized health, role dashboard, audit metrics, live events, WebSocket broadcasting

### Changed
- `cm_runtime_service.py` — Full rewrite from placeholder to real DB query logic
- `worker_runtime_service.py` — Full rewrite from placeholder to real DB query logic
- `security_runtime_service.py` — Full rewrite from placeholder to real DB query logic
- `system_health_normalized.py` — Enriched contract with additional fields
- `system_health_dashboard.py` — Real panel data from MongoDB queries
- `SystemHealthDashboard.js` — Complete overhaul with WebSocket, role-based UI, live events
- `App.js` — Added ErrorBoundary import and wrapping
- `pyproject.toml` — Added asyncio_default_fixture_loop_scope for test stability
- `bootstrap/router_registry.py` — Registered new system_health_live router

### Test Results
- Backend: 30/30 tests passed (100%)
- Frontend: All dashboard elements verified by testing agent
- Full regression: PASSED
