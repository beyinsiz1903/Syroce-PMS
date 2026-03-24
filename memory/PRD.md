# Syroce PMS — Product Requirements Document

## Original Problem Statement
Full-stack hotel Property Management System (PMS) with multi-tenant architecture, channel manager integration (Exely), ARI outbound, and enterprise features.

## Core Architecture
- **Backend:** FastAPI + MongoDB (Motor async driver)
- **Frontend:** React + Vite + Shadcn UI
- **Multi-tenant:** TenantAwareDBProxy with context-based isolation
- **Workers:** Outbox worker, Import retry worker, ARI push worker, Room type inventory worker, Night audit
- **CI/CD:** GitHub Actions with ruff linting, orphan/boundary guards

## Technical Debt Cleanup Phases

### Phase A: Truth Drift Cleanup — DONE
- Cleaned `frontend/package.json` (removed CRA deps)
- Regenerated `yarn.lock`
- Updated all READMEs

### Phase C: Backend Organization — DONE
- Moved 25 top-level Python files into `domains/`, `infra/`, `modules/`, `_legacy/`
- Updated all import paths across backend

### Phase B: CI/CD Hardening
- **Wave 1 — DONE:** Fixed F811/F841 ruff violations, enabled rules
- **Wave 2 — DONE:** Enabled I (isort) + F401 (unused imports), fixed 767 violations, cleaned exclude list
- Wave 3: Stricter formatting rules (PENDING)
- Wave 4: Node.js 20→22 upgrade (PENDING)
- Final: Remove `|| true` from ci-cd.yml (PENDING)

### Phase D: Frontend Refactoring — PENDING
- Refactor monolithic App.jsx into route config

## Strict Tenant Mode — DONE (2026-03-24)
- `STRICT_TENANT_MODE=true` enabled in production
- `SchemaOnlyCollection`: allows index creation, blocks data operations without tenant context
- All workers use `get_system_db()` for cross-tenant queries, `tenant_context()` for per-tenant processing
- Auth router uses `get_system_db()` for system-level operations
- `startup.py` uses `_raw_db` for all system operations

## Wire Failure Tracking — DONE (2026-03-24)
- FailureTracker integrated into ARI push worker
- Unified wire status API: `GET /api/wire-status`
- Wire failures API: `GET /api/wire-status/failures`
- End-to-end failure chain: Import Bridge → Outbox → ARI Push

## CI Regression Guards — DONE (2026-03-24)
- Orphan-file guard: `scripts/check_orphan_files.py` (19 allowed root files)
- Import boundary guard: `scripts/check_import_boundaries.py` (3 known exceptions tracked)
- Both added to GitHub Actions as hard gates

## Upcoming Tasks (Priority Order)
1. **P0:** Phase B Wave 3 — Stricter ruff formatting rules
2. **P0:** Phase B Wave 4 — Node.js 20→22 in GitHub Actions
3. **P0:** Phase B Final — Remove `|| true` from ci-cd.yml
4. **P1:** Phase D — Frontend App.jsx refactoring
5. **P1:** Load + chaos testing
6. **P2:** pms.py decomposition

## Key API Endpoints
- `GET /health` — Health check
- `POST /api/auth/login` — Authentication
- `GET /api/pms/rooms` — Room management
- `GET /api/wire-status` — Unified wire status
- `GET /api/wire-status/failures` — Wire failure list

## Test Credentials
- Email: `demo@hotel.com`, Password: `demo123`
