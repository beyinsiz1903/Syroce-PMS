# Syroce Hotel PMS — Changelog

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
