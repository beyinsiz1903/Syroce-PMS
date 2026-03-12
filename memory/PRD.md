# Hotel Operating System — Product Requirements Document

## Overview
Enterprise hotel operating system (Syroce Hotel Management) — multi-tenant SaaS platform for hotel operations management.

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async)
- **Frontend**: React + Shadcn/UI
- **Pattern**: `router -> service -> repository` (Domain-Driven Design)
- **Common Contracts**: `ServiceResult`, `OperationContext`, `DomainError` hierarchy
- **Auth**: JWT-based with RBAC (super_admin, admin, gm, receptionist, etc.)
- **Multi-tenant**: Strict tenant isolation via `tenant_id` on all queries

## Core Domains
- **PMS**: Rooms, Reservations, Front Desk, Housekeeping, Night Audit
- **Revenue**: Pricing, RMS (Revenue Management), Folio/Finance
- **Guest**: Messaging, Profiles, Loyalty
- **Channel Manager**: OTA sync, Drift detection, Reconciliation
- **Operations**: POS/F&B, Mobile Ops, Maintenance
- **Runtime Hardening**: Worker health, Security, Observability

## Completed Features

### Phase A: Schema Organization (DONE)
- 10+ domain `schemas.py` files extracted from inline Pydantic models
- Domains: reservations, rooms, folio, guest, channel_manager, worker, security, pos_fnb, mobile, pricing, rms, messaging

### Phase B: Service Wiring (DONE)
**Hardening Services** (Session 1):
- `CMRuntimeService`, `WorkerRuntimeService`, `SecurityRuntimeService`

**Core PMS Services** (Session 2):
- `FrontdeskService` — check-in, check-out, arrivals, departures, keycard, guest alerts, audit checklist, unified views
- `NightAuditService` — audit logs, error logs, night audit logs, OTA sync logs, RMS publish logs, maintenance predictions
- `PricingService` — rate plans, demand forecast, competitor rates, dynamic pricing, revenue dashboard
- `RmsService` — group bookings, corporate contracts, OTA promotions, inventory, yield analysis
- `MessagingService` — guest messaging, internal messaging, templates
- `MobileOpsService` — no-show, room change, quick tasks, quick issues, mobile dashboard
- `PosFnbService` — kitchen display, orders, table layout, F&B dashboard, stock management

### Phase C: Frontend System Health Dashboard (DONE)
- `/system-health` route with 4 metric cards + 4 panel cards
- Normalized overview bar with overall status, severity, scope, role
- Subsystem health cards (channel_manager, workers, security, observability)
- WebSocket connection status indicator
- Live events strip (ready for WebSocket connection)

### Phase D: Backend API Normalization (DONE)
- `/api/system-health/normalized/overview` — aggregated health across all subsystems
- `/api/system-health/normalized/channel-manager` — standardized channel manager health
- `/api/system-health/normalized/workers` — standardized worker health
- `/api/system-health/normalized/security` — standardized security health
- `/api/system-health/normalized/observability` — standardized observability health
- `/api/system-health/role-dashboard` — role-based data shaping (GM/Admin/Superadmin)
- Standard fields: `status`, `severity`, `scope_type`, `scope_id`, `last_updated_at`, `action_available`, `suggested_action`, `live_capable`

### Phase F: Testing (DONE)
- **Service wiring tests**: 52 tests (19 new Phase 2 + 33 existing Phase 1)
- **Runtime stress tests**: 6 tests (OTA burst, concurrent check-in, queue saturation, stuck task detection, tenant isolation)
- **Integration tests**: 16 tests by testing agent (normalized API + service-wired endpoints + frontend)
- **Load test framework**: k6 scenarios for OTA burst, system health dashboard, night audit

## Remaining / P1 Tasks
1. **WebSocket Live Updates**: Connect frontend to Socket.IO `system-health` room for real-time event streaming
2. **Audit & Observability Enrichment**: Add service-level audit hooks and operation duration metrics
3. **Frontend Stabilization**: Route-based code splitting, error boundaries, loading state patterns

## Backlog / P2 Tasks
1. **Hardening Logic**: Replace placeholder data in CMRuntimeService, WorkerRuntimeService, SecurityRuntimeService with real business logic
2. **Comprehensive Hardening Tests**: Stress tests and regression for channel manager, worker, security features
3. **Frontend Code Splitting**: Module boundaries for frontdesk, housekeeping, finance, admin, runtime health, messaging

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
