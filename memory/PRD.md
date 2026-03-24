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
Operational APIs for secrets management with rotation, rollback, and visibility.

## SEC-002 Crypto Migration Rollout (COMPLETED - March 2026)
Operational APIs for crypto migration status and cutover readiness.

## Sandbox Dashboard Visualization (COMPLETED - March 2026)
Full ops dashboard integration for sandbox simulation results.

## /api/ops/* Admin Guard (COMPLETED - March 2026)
Role-based access control for all operational endpoints.

## Alert -> Business KPI Correlation (COMPLETED - March 2026)
Enhanced alerts with severity, runbook links, tenant/provider context.

## CI/CD Pipeline Sandbox Integration (COMPLETED - March 2026)
### What was built:
3-tier sandbox validation integrated into CI/CD pipeline for deploy confidence.

1. **PR Gate** (`POST /api/ops/cicd/run tier=pr_gate`):
   - Quick subset: 5 scenarios, 2 providers, low concurrency (duplicate_count=3, storm_size=6)
   - Blocks deploy on failure
   - Health label: `sandbox_validation`

2. **Staging Gate** (`POST /api/ops/cicd/run tier=staging_gate`):
   - Full scenario pack: all 5 scenarios, 2 providers, standard concurrency (duplicate_count=5, storm_size=10)
   - Blocks deploy on failure
   - Health label: `staging_deploy_validation`

3. **Nightly Resilience** (`POST /api/ops/cicd/run tier=nightly`):
   - Heavy set: all scenarios, high concurrency (duplicate_count=10, storm_size=25)
   - Does NOT block deploy, produces confidence signal
   - Health label: `prod_health`

4. **Acceptance Criteria Evaluator**: Each run evaluates:
   - Exely sandbox: all critical PASS
   - HotelRunner sandbox: all critical PASS
   - oversell: 0
   - duplicate inventory consumption: 0
   - inconsistent state: 0
   - stale provider recovery: PASS
   - reconciliation recovery: PASS
   - deterministic modify/cancel: PASS
   - new regression vs baseline: 0 critical

5. **Deploy Gate Verdict**: PASS / BLOCK / WARN with failure details and runbook links

6. **Health Badges**: 3 separate badges (sandbox_validation, staging_deploy_validation, prod_health) — never mixed

7. **Results to Dashboard**: build_id, commit_sha, deploy_id, provider result, scenario result, regression status, runbook links

8. **Runbook per Failure**: Every fail case includes severity, impact, runbook link, rollback suggestion

### API Endpoints:
- `GET /api/ops/cicd/tiers` — Available tier configurations
- `POST /api/ops/cicd/run` — Trigger pipeline run
- `GET /api/ops/cicd/runs` — List recent runs
- `GET /api/ops/cicd/runs/{run_id}` — Specific run details
- `GET /api/ops/cicd/deploy-gate/{run_id}` — Deploy gate verdict
- `GET /api/ops/cicd/baseline` — Last passing baselines
- `GET /api/ops/cicd/health-badges` — Separate health badges
- `GET /api/ops/cicd/trends` — Pipeline trend data

### Frontend:
- `CICDPipelineDashboard.jsx` — Health badges, tier trigger buttons, trend chart, recent runs with drill-down
- Integrated into `UnifiedOpsView.jsx` on `/control-plane` page

## CI/CD Pipeline GitHub Actions Fix (February 2026)
### What was fixed:
1. **docker-build failure**: Added `--ignore-engines` flag to Dockerfile `yarn install` + copied `scripts/` directory before `yarn install` (postinstall hook needs `patch-vite-client.js`) + regenerated `yarn.lock`
2. **Node.js 20 deprecation warnings**: Upgraded all GitHub Action versions to Node.js 24 compatible:
   - `actions/checkout@v4` → `@v5`
   - `actions/setup-node@v4` → `@v5`
   - `actions/upload-artifact@v4` → `@v5`
   - `docker/login-action@v3` → `@v4`
   - `docker/setup-buildx-action@v3` → `@v4`
   - `docker/build-push-action@v5` → `@v6`
3. Added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` env var to both workflows

## Codebase Truth Cleanup & Backend Organization (February 2026)
### Faz A — package.json & README (COMPLETED)
1. Removed CRA-era `browserslist` config from `package.json`
2. Removed CRA-era `jest` config from `package.json`
3. Updated `package.json` name: `frontend` → `syroce-frontend`, version: `0.1.0` → `2.1.0`
4. Regenerated `yarn.lock` (clean tree, 0 high/critical vulnerabilities)
5. Updated README architecture section and version info

### Faz C — Backend File Organization (COMPLETED)
Moved 25 orphan files from `backend/` root to proper domain directories:
- **AI Domain (7 files)**: `ai_service.py`, `ai_endpoints.py`, `predictive_engine.py`, `reputation_manager.py`, `social_media_radar.py`, `revenue_autopilot.py`, `dynamic_pricing_engine.py` → `domains/ai/`
- **PMS Domain (6 files)**: `group_sales_models.py`, `housekeeping_ai.py`, `hotel_inventory_system.py`, `night_audit_module.py`, `booking_adapter.py`, `room_block_models.py` → `domains/pms/`
- **Guest Domain (2 files)**: `online_checkin_models.py`, `whatsapp_service.py` → `domains/guest/`
- **Admin Domain (1 file)**: `subscription_models.py` → `domains/admin/`
- **Infra (7 files)**: `cdn_headers.py`, `security_headers.py`, `prometheus_metrics.py`, `logging_service.py`, `database_optimizer.py`, `simple_cache.py`, `report_automation.py` → `infra/` / `modules/`
- **Legacy (1 file)**: `graphql_schema.py` → `_legacy/`
- All import references updated across codebase (0 import errors)

### Faz B — CI/CD Lint Hardening, First Wave (COMPLETED)
1. Added `F811` (redefinition-of-unused) and `F841` (unused-variable) to ruff rules
2. Fixed 16 F811 violations: renamed duplicate route handlers, removed dead model definitions
3. Fixed 6 F841 violations: prefixed unused variables with `_`
4. Removed duplicate `MarketSegment` enum, `FolioCharge` class, `RatePlan` class
5. Removed unused `date` import from `models/schemas.py`

### Remaining Backend Orphans (13 files — deferred to Faz C-2):
Infrastructure cluster with high cross-references: `cache_manager.py` (21 refs), `websocket_server.py` (12 refs), `cache_warmer.py` (6 refs), `redis_cache.py` (5 refs), `ml_data_generators.py` (5 refs), `ml_trainers.py` (5 refs), `apm_middleware.py` (4 refs), `materialized_views.py` (4 refs), `celery_app.py` (3 refs), `celery_tasks.py` (1 ref), `data_archival.py` (3 refs), `optimization_endpoints.py` (3 refs), `advanced_cache.py` (2 refs)

## Key Endpoints
- `POST /api/auth/login` -> `{access_token, user, tenant}`
- `GET /api/pms/operational-alerts` -> `{alerts[], summary{}, available_clean_rooms[]}`
- `POST /api/channel-manager/v2/sandbox/simulate` -> simulation report
- `GET /api/ops/secrets/status` -> secrets health
- `GET /api/ops/crypto/status` -> crypto health
- `GET /api/ops/crypto/cutover-metrics` -> migration progress
- `GET /api/ops/sandbox/dashboard` -> sandbox provider cards
- `GET /api/ops/sandbox/trends` -> pass rate trends
- `GET /api/ops/alerts/kpi-correlation` -> business impact mapping
- `POST /api/ops/cicd/run` -> CI/CD pipeline run with deploy gate verdict
- `GET /api/ops/cicd/health-badges` -> separate health badges
- `GET /api/ops/cicd/trends` -> pipeline trend data

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Backlog (P2)
- Wire failure tracking (import bridge, outbox worker, ARI push engine)
- Strict Tenant Mode (`STRICT_TENANT_MODE=true`)
- Legacy db import migration (~264 imports)
- pms.py decomposition (2714 lines -> modular services)
- Legacy collection cleanup (~489 collections)
- Load and chaos testing
- Faz C-2: Move remaining 13 infra orphan files (cache_manager, websocket_server, etc.)
- Faz B-2: Ruff import sorting rules
- Faz B-3: Node.js 20 → 22 LTS upgrade in CI workflows (separate PR)

## Backlog (P3)
- Faz D: App.jsx route-config refactoring (requires route snapshot + smoke tests first)
- Vite production build + Nginx
- Go-live runbook, SLO/SLA docs
- AWS KMS, HashiCorp Vault integration
- PII masking, stress testing
- Motor -> pymongo async migration
- HMR guard decommission
- Configure Slack webhook for production alerts
