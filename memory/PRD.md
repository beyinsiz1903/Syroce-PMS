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

## Remaining Backlog

### P0
- Complete service wiring for pos_fnb, rms, mobile routers

### P1
- Role-based dashboard UI polish (conditional rendering by role)
- Full frontend code splitting for all modules

### P2
- Flesh out stress test logic in tests/runtime/ files
- Flesh out load test logic in load_tests/ files
- Implement real business logic in all service placeholder methods
- Service business logic for FrontdeskService, NightAuditService, etc.
- Audit & observability hooks within service methods

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

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
