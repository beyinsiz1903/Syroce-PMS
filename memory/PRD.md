# Syroce PMS — Product Requirements Document

## Original Problem Statement
Enterprise otel yonetim sistemi (PMS). Operasyonel zeka platformu: channel manager entegrasyonu, drift algilama, auto-reconciliation, deploy tracking, KPI metrikleri. Frontend'in "data-driven"dan "decision-driven"a donusumu hedefleniyor.

## Core User Personas
- **Resepsiyonist**: Check-in/out, misafir yonetimi, odeme alma
- **Kat Hizmetleri**: Oda temizlik durumu takibi
- **Genel Mudur**: Operasyonel overview, KPI analiz
- **Rezervasyon Yoneticisi**: Kanal yonetimi, fiyatlandirma

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
  - Upstream compatibility check: `scripts/check-vite-compat.js`
  - Regression tests: 8 tests in `backend/tests/test_hmr_patch.py`

## Phase A-I (COMPLETED)
All foundational layers: Notification, Auto-Action Engine, Unified Ops View, Control Plane, Channel Health, Drift Alerting, Import Bridge, Outbox Worker, ARI Push Engine, Crypto/Secrets modules.

## Decision-Driven UX Transformation (COMPLETED - March 2026)
Dashboard Command Center, Enhanced Room Board, Upgraded Front Desk, Smart Payment Dialog, Reservation Detail Ops Panel, Room Alternatives API.

## P1 Sandbox Simulation (COMPLETED - March 2026)
Channel Manager resilience testing framework: 5 scenarios, 2 providers (HotelRunner + Exely). 10/10 pass rate.

## SEC-001 Secrets Management Rollout (COMPLETED - March 2026)
### What was built:
Operational APIs for secrets management with rotation, rollback, and visibility.

1. **Secrets Status** (`GET /api/ops/secrets/status`): Health, provider config, audit stats, anomaly counts
2. **Rotation Plan** (`GET /api/ops/secrets/rotation-plan`): Per-secret age tracking, severity ratings (OK/ROTATE_RECOMMENDED/ROTATE_URGENT), rollback availability
3. **Rotate** (`POST /api/ops/secrets/rotate`): Credential rotation with previous version preserved
4. **Rollback** (`POST /api/ops/secrets/rollback`): Restore previous credential version
5. **Scoping** (`GET /api/ops/secrets/scoping`): Tenant/provider/property isolation view

## SEC-002 Crypto Migration Rollout (COMPLETED - March 2026)
### What was built:
Operational APIs for crypto migration status and cutover readiness.

1. **Crypto Status** (`GET /api/ops/crypto/status`): V2/V1 state, dual-read/write config, fallback strategy, key versioning
2. **Cutover Metrics** (`GET /api/ops/crypto/cutover-metrics`): Format distribution (SYR1 vs AES-GCM vs legacy), migration percentage, cutover readiness
3. **Migration Dry-Run** (`POST /api/ops/crypto/migrate-check`): Scan without writing, shows migration candidates
4. **Key Info** (`GET /api/ops/crypto/key-info`): Key versioning, rotation steps, rollback plan (immediate, break-glass, key rollback)

## Sandbox Dashboard Visualization (COMPLETED - March 2026)
### What was built:
Full ops dashboard integration for sandbox simulation results.

1. **Provider Cards**: Exely/HotelRunner pass/fail with scenario-level drill-down
2. **Trend Chart**: Pass rate over last 30 runs with Recharts visualization
3. **Regression Detection**: Compares last 2 runs, flags scenarios that regressed
4. **Correlation**: Links sandbox results to deploys and drift events
5. **Labels**: `sandbox_pass` / `sandbox_regression` / `prod_health` separation

## /api/ops/* Admin Guard (COMPLETED - March 2026)
Role-based access control for all operational endpoints. Requires `super_admin`, `admin`, `operator`, or `manager` role. Returns 401 without token, 403 for insufficient role.

## Alert → Business KPI Correlation (COMPLETED - March 2026)
### What was built:
1. **Enhanced Alerts**: All alerts now include `severity`, `runbook_link`, `tenant_id`, `property_id`, `provider` fields
2. **KPI Correlation** (`GET /api/ops/alerts/kpi-correlation`): Maps alerts to business impact:
   - Import failures → revenue_risk
   - Outbox stuck → rate_parity_risk
   - Secret anomalies → security_risk
   - Crypto failures → data_protection_risk
3. **Webhook Enhancement**: Slack-compatible payloads now include tenant/provider context

## Key Endpoints
- `POST /api/auth/login` → `{access_token, user, tenant}`
- `GET /api/pms/operational-alerts` → `{alerts[], summary{}, available_clean_rooms[]}`
- `POST /api/channel-manager/v2/sandbox/simulate` → simulation report
- `GET /api/ops/secrets/status` → secrets health
- `GET /api/ops/crypto/status` → crypto health
- `GET /api/ops/crypto/cutover-metrics` → migration progress
- `GET /api/ops/sandbox/dashboard` → sandbox provider cards
- `GET /api/ops/sandbox/trends` → pass rate trends
- `GET /api/ops/alerts/kpi-correlation` → business impact mapping

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Backlog (P2)
- Wire failure tracking (import bridge, outbox worker, ARI push engine)
- Strict Tenant Mode (`STRICT_TENANT_MODE=true`)
- Legacy db import migration (~264 imports)
- pms.py decomposition (2714 lines → modular services)
- Legacy collection cleanup (~489 collections)
- Load and chaos testing

## Backlog (P3)
- Vite production build + Nginx
- Go-live runbook, SLO/SLA docs
- AWS KMS, HashiCorp Vault integration
- PII masking, stress testing
- Motor → pymongo async migration
- HMR guard decommission
- Configure Slack webhook for production alerts
