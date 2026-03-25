# PMS (Property Management System) - PRD

## Original Problem Statement
Hotel Property Management System - full-stack application with React frontend and FastAPI backend with MongoDB. Multi-tenant PMS with booking management, room management, guest profiles, channel manager integration, enterprise features.

## User Personas
- Hotel managers and staff who manage bookings, rooms, guests, and operations.

## Project Priorities (User-Defined)

### P0 - Go-Live Hardening ✅ COMPLETED
- Vite production build optimized
- Nginx hardened
- Go-Live Runbook, SLO/SLA, Incident Playbook created

### P1 - Critical Fixes & Improvements ✅ COMPLETED
- `room-move-history` endpoint bug fix — schema normalized to canonical fields
- Load test suite expanded — multi-tenant, failure injection, retry storm, queue backlog, reconciliation
- Import boundary violations resolved — 3/3 exceptions eliminated
- CI orphan file guard fix — `create_test_user.py` moved to `scripts/`

### P2 - Code Quality & Refactoring (BACKLOG)
- Ruff UP rules
- App.jsx decomposition

## Architecture
- Frontend: React + Vite + Shadcn UI
- Backend: FastAPI + Motor (async MongoDB)
- Database: MongoDB (hotel_pms)
- CI/CD: GitHub Actions

## What's Been Implemented
- Full PMS functionality (bookings, rooms, guests, housekeeping, etc.)
- Channel manager integrations (Exely, Booking.com adapter)
- Enterprise features (analytics, reports, revenue management)
- Go-Live Hardening (P0) - completed
- All P1 critical fixes and improvements - completed
- Comprehensive load test suite (5 files covering 30+ scenarios)
- Clean import boundaries with zero violations
- CI guards: orphan files + import boundaries

## Key Files
- Backend entry: `/app/backend/server.py`
- Frontend entry: `/app/frontend/src/App.jsx`
- Routers: `/app/backend/routers/`
- Load tests: `/app/backend/load_tests/`
- CI scripts: `/app/backend/scripts/`
- Docs: `/app/docs/`
- CI: `/.github/workflows/ci-cd.yml`

## Test Credentials
- Email: demo@hotel.com / Password: demo123

## Key Decisions
- BlockStatus/BlockType enums moved to `models/enums.py` (shared)
- BookingAdapter moved to `integrations/booking_adapter.py` (canonical location)
- Worker health exposed via `core/worker_health.py` facade (layer boundary)
- Room move history uses canonical fields: from_room_number, to_room_number, moved_at
