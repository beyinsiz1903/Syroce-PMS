# Syroce PMS — Product Requirements Document

## Original Problem Statement
Enterprise otel yönetim sistemi (PMS). Operasyonel zeka platformu: channel manager entegrasyonu, drift algılama, auto-reconciliation, deploy tracking, KPI metrikleri. Frontend'in "data-driven"dan "decision-driven"a dönüşümü hedefleniyor.

## Core User Personas
- **Resepsiyonist**: Check-in/out, misafir yönetimi, ödeme alma
- **Kat Hizmetleri**: Oda temizlik durumu takibi
- **Genel Müdür**: Operasyonel overview, KPI analiz
- **Rezervasyon Yöneticisi**: Kanal yönetimi, fiyatlandırma

## Tech Stack
- **Frontend**: React + Vite + Shadcn/UI + Tailwind + Manrope font
- **Backend**: FastAPI + MongoDB (motor async) + Python
- **Auth**: JWT-based custom auth

## Architecture
- Backend: `/app/backend/` (FastAPI, routers in `/app/backend/routers/`)
- Frontend: `/app/frontend/src/` (React, pages + components)
- axios baseURL: `VITE_BACKEND_URL + '/api'`

## Bug Fixes
- **HMR Page Auto-Refresh (Permanent Fix - March 2026):**
  - 3-layer defense: postinstall patch, build-time transform, runtime guard
  - Runtime guard now behind `VITE_HMR_GUARD_ENABLED` feature flag
  - Upstream compatibility check: `scripts/check-vite-compat.js` — detects Vite client changes
  - Regression tests: 8 tests in `backend/tests/test_hmr_patch.py`

## Phase A-I (COMPLETED)
All foundational layers: Notification, Auto-Action Engine, Unified Ops View, Control Plane, Channel Health, Drift Alerting, Import Bridge, Outbox Worker, ARI Push Engine, Crypto/Secrets modules.

## Decision-Driven UX Transformation (COMPLETED - March 2026)
Dashboard Command Center, Enhanced Room Board, Upgraded Front Desk, Smart Payment Dialog, Reservation Detail Ops Panel, Room Alternatives API.

## P1 Sandbox Simulation (COMPLETED - March 2026)
### What was built:
Channel Manager resilience testing framework with 5 scenarios, 2 providers (HotelRunner + Exely).

1. **Provider Harness** (`sandbox_simulation/provider_harness.py`):
   - Synthetic data generators for HotelRunner and Exely
   - Configurable reservation generation with chaos injection

2. **5 Resilience Scenarios** (`sandbox_simulation/scenarios.py`):
   - **Duplicate Delivery**: Same reservation sent N times → 0 double inventory consumption
   - **Delayed Acknowledgment**: ACK failure + retry → 0 inconsistent state
   - **Retry Storm**: Provider resends same batch → 0 oversell, idempotent import
   - **Stale Provider State**: Old availability data → reconciliation detects drift & recovers
   - **Modify/Cancel Race**: new → modify → cancel sequence → deterministic outcome

3. **Simulation Engine** (`sandbox_simulation/engine.py`):
   - Orchestrates all scenarios per provider
   - Creates sandbox fixtures (connectors, mappings) with unique property IDs
   - Generates per-provider result tables with pass_rate
   - Persists results and event timeline to MongoDB

4. **API Endpoints** (`routers/sandbox_router.py`):
   - `POST /api/channel-manager/v2/sandbox/simulate` — Run simulation
   - `GET /api/channel-manager/v2/sandbox/results` — List results
   - `GET /api/channel-manager/v2/sandbox/results/{run_id}` — Specific result
   - `GET /api/channel-manager/v2/sandbox/timeline/{run_id}` — Event timeline
   - `DELETE /api/channel-manager/v2/sandbox/cleanup/{run_id}` — Clean up

5. **Testing**: 24/24 tests pass (9 unit + 15 API)

### Done Criteria Met:
| Criteria | Result |
|----------|--------|
| duplicate delivery → 0 double inventory | ✅ PASS |
| delayed ack → 0 inconsistent state | ✅ PASS |
| retry storm → 0 oversell | ✅ PASS |
| stale provider state → reconciliation recovers | ✅ PASS |
| modify/cancel races → deterministic | ✅ PASS |
| Exely separate result table | ✅ PASS |
| HotelRunner separate result table | ✅ PASS |
| Events in timeline | ✅ PASS (46 events per run) |

## Key Endpoints
- `POST /api/auth/login` → `{access_token, user, tenant}`
- `GET /api/pms/operational-alerts` → `{alerts[], summary{}, available_clean_rooms[]}`
- `GET /api/pms/room-alternatives/{room_number}` → `{same_type[], other_type[]}`
- `POST /api/channel-manager/v2/sandbox/simulate` → simulation report
- `GET /api/channel-manager/v2/sandbox/results` → recent results
- `GET /api/channel-manager/v2/sandbox/timeline/{run_id}` → event timeline

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Backlog (P1 — Next)
- SEC-001 Secrets Management — rotation + rollback plan, tenant/provider-scoped, access audit trail
- SEC-002 Crypto Migration — dual-read/dual-write, migration cutover metric, failed decrypt fallback, key versioning

## Backlog (P1.5)
- Alert → Business KPI Correlation — severity + runbook link + tenant/property/provider context

## Backlog (P2)
- Wire failure tracking (import bridge, outbox worker, ARI push engine)
- `/api/ops/*` admin guard protection
- Strict Tenant Mode
- Legacy db import migration (~264 imports)
- pms.py decomposition (2714 lines → modular services)
- Legacy collection cleanup (~489 collections)

## Backlog (P3)
- Vite production build + Nginx
- Go-live runbook, SLO/SLA docs
- AWS KMS, HashiCorp Vault
- PII masking, stress testing
- Motor → pymongo migration
- HMR guard decommission (when proxy/WebSocket/HMR chain is natively stable)
