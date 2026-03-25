# PMS (Property Management System) - PRD

## Original Problem Statement
Hotel Property Management System - full-stack application with React frontend and FastAPI backend with MongoDB.

## User Personas
- Hotel managers and staff who manage bookings, rooms, guests, and operations.

## Core Requirements
1. Multi-tenant hotel PMS with booking management, room management, guest profiles
2. Channel manager integration (HotelRunner, Exely, etc.)
3. Enterprise features: analytics, reporting, revenue management
4. Production-ready deployment with CI/CD pipeline

## Project Priorities (User-Defined)
- **P0 - Go-Live Hardening** ✅ COMPLETED
  - Vite production build optimized
  - Nginx hardened
  - Go-Live Runbook, SLO/SLA, Incident Playbook created
- **P1 - Critical Fixes & Improvements** (IN PROGRESS)
  - `room-move-history` endpoint bug fix
  - Load test suite expansion
  - Import boundary cleanup
- **P2 - Code Quality & Refactoring**
  - Ruff UP rules
  - App.jsx decomposition

## Architecture
- Frontend: React + Vite + Shadcn UI
- Backend: FastAPI + Motor (async MongoDB)
- Database: MongoDB
- CI/CD: GitHub Actions

## What's Been Implemented
- Full PMS functionality (bookings, rooms, guests, housekeeping, etc.)
- Channel manager integrations
- Enterprise features (analytics, reports, revenue management)
- Go-Live Hardening (P0) - completed
- CI fixes and linting cleanup
- Orphan file CI fix: `create_test_user.py` moved to `scripts/` (Feb 2026)

## Key Files
- Backend entry: `/app/backend/server.py`
- Frontend entry: `/app/frontend/src/App.jsx`
- Routers: `/app/backend/routers/`
- Docs: `/app/docs/`
- CI: `/.github/workflows/ci-cd.yml`

## Test Credentials
- Email: demo@hotel.com / Password: password
- Email: test@hotel.com / Password: test123
