# Syroce PMS — Product Requirements Document

## Original Problem Statement
Full-stack hotel PMS (Property Management System) application with multi-tenant architecture, booking management, room inventory, channel management, and CI/CD pipeline.

## Architecture
- **Frontend:** React (Vite 8 + Rolldown) with Shadcn/UI, TailwindCSS
- **Backend:** FastAPI (Python) with MongoDB (motor async driver)
- **Database:** MongoDB
- **CI/CD:** GitHub Actions with curated test suite

## Core Features Implemented
- Multi-tenant booking management with atomic room-night locking
- Room type system with inventory management
- Channel manager integration (Exely, HotelRunner)
- Hold/OOO (Out of Order) room management
- AI Chatbot for hotel operations
- Audit trail & timeline events
- Crypto engine for sensitive data
- Outbox pattern for reliable event publishing
- Comprehensive battle test suite (348+ tests)

## What's Been Completed

### CI/CD Pipeline Stability (Latest)
- **Frontend Build Fix:** Renamed all `.js` → `.jsx` files (356 files) to fix Vite 8/Rolldown JSX parsing error in production builds. Rolldown 1.0.0-rc.10 doesn't support `oxc.lang: 'jsx'` for `.js` files in bundled build mode.
- **Flaky Test Fix:** Widened `_RUN_TAG` random range from 40 values (2050-2090) to 7900 values (2100-9999). Added `conftest.py` with session-scoped auto-cleanup fixture to remove stale test locks.
- **yarn audit Fix:** Implemented bitmask-based exit code handling to only fail on HIGH/CRITICAL vulnerabilities.
- **CI env vars:** Fixed `REACT_APP_BACKEND_URL` → `VITE_BACKEND_URL` for Vite 8 compatibility.
- **ESLint `ajv` Fix:** Both `resolutions` (yarn) and `overrides` (npm) configured in `package.json`.
- **`websocket.js` Fix:** Corrected async/await usage.

### Previous Work
- Complete booking lifecycle with atomic locking
- Room type inventory system
- Multi-phase hardening test suites
- Resilience testing (provider failures, chaos engineering)
- Control plane tests
- Import bridge functionality

## P0 — Completed
- [x] Frontend production build (Vite 8/Rolldown compatibility)
- [x] Flaky backend test stabilization
- [x] CI/CD pipeline reliability (yarn audit, env vars)

## P1 — Upcoming
- [ ] Address quarantined tests in `tests/_quarantine/` (7 directories)
- [ ] Channel manager inventory ledger alignment with room-type system

## P2 — Backlog
- [ ] Crypto Migration (SEC-002)
- [ ] Secrets Management Rollout (SEC-001)
- [ ] Enable Strict Tenant Mode
- [ ] motor → pymongo native async migration
- [ ] Production build with Nginx static serving
- [ ] ~264 legacy DB import cleanup
- [ ] Governance Phase 3-4 (Support/KPI Dashboard)

## Key Technical Decisions
- **Vite 8 `.jsx` Convention:** All React component files use `.jsx` extension. This is required because Rolldown's native `viteTransformPlugin` doesn't support `oxc.lang: 'jsx'` for `.js` files in build mode.
- **Test Isolation:** Battle tests use `random.randint(2100, 9999)` for date ranges + session-scoped DB cleanup via `conftest.py`.
- **yarn audit CI Gate:** Uses bitmask check `(exit_code & 24) != 0` to only fail on HIGH (8) or CRITICAL (16) vulnerabilities.

## Test Credentials
| User | Email | Password | Role |
|:---|:---|:---|:---|
| Demo Admin | demo@hotel.com | demo123 | super_admin |
