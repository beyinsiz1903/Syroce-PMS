# Syroce PMS — Product Requirements Document

## Original Problem Statement
Hotel management system (PMS) with multi-tenant architecture. Current focus: technical debt reduction and CI/CD hardening.

## Architecture
- **Backend**: FastAPI + MongoDB (strict tenant mode active)
- **Frontend**: React (Vite)
- **Auth**: JWT-based with tenant isolation
- **CI/CD**: GitHub Actions with hard gates

## What's Been Implemented

### Sprint 1 (Previous Session)
- Strict Tenant Mode (`STRICT_TENANT_MODE=true`)
- Wire Failure Tracking (`/api/wire-status`)
- Ruff Wave 2 (I001, F401 rules)
- CI Guards (orphan-file, import-boundary checks)

### Sprint 2 (Current Session - 2026-03-24)
- **CI/CD Final — `|| true` removal**: Channel Health smoke test hardened to hard gate. Seed script now fails-fast. Justified `|| true` entries (Slack, grep) documented with inline comments.
- **CI/CD Wave 3 — Ruff stricter rules**: Added `W` (whitespace) and `C4` (comprehensions) rules. ~5800 violations auto-fixed. Zero remaining violations.
- **CI/CD Wave 4 — Node.js upgrade**: NODE_VERSION 20 → 22 in GitHub Actions.
- **Security Ignore Registry**: Created `/app/backend/docs/SECURITY_IGNORE_REGISTRY.md` with reason, expiry, owner for each CVE ignore.
- **pms.py Decomposition Stage 1**: Extracted rooms (9 routes, 611 lines) and guests (5 routes, 164 lines) into `pms_rooms.py` and `pms_guests.py`. pms.py reduced from 2934 → 2194 lines. 59/59 route wiring regression test passes.
- **Outbox test fix**: Updated 5 tests in `test_outbox_pattern.py` to use `patch("core.outbox_worker.get_system_db")` instead of non-existent `db` attribute.

## Prioritized Backlog

### P0 — In Progress
- **pms.py Decomposition Stage 2**: Extract bookings + dashboard routes
- **pms.py Decomposition Stage 3**: Extract remaining routes (reservations, availability, queue, services)

### P1 — Next
- Load + Chaos Testing
- Frontend refactoring (App.jsx decomposition)
- Import Boundary exceptions (3 known)

### P2 — Future
- UP (pyupgrade) rules — 9018 violations, large scope
- B (bugbear) rules — B008 false positives with FastAPI Depends()

## Test Reports
- `/app/test_reports/iteration_152.json` — Sprint 1 final
- `/app/test_reports/iteration_153.json` — Sprint 2 (CI/CD + Stage 1 decomposition)

## Credentials
- Email: `demo@hotel.com`, Password: `demo123`
