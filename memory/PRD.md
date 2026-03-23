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
  - **Root cause:** Kubernetes proxy drops idle WebSocket connections after ~60s. Vite HMR client and `emergent-main.js` call `location.reload()` on disconnect.
  - **Fix: 3-layer defense (permanent, survives `yarn install`):**
    1. **Postinstall script** (`scripts/patch-vite-client.js`): Automatically patches `node_modules/vite/dist/client/client.mjs` after every `yarn install`, replacing `location.reload()` with console.debug.
    2. **Vite plugin transform hook** (`hmrReloadGuard`): Build-time backup that catches reload calls in bundled client code.
    3. **Runtime guard** (`transformIndexHtml`): Injects smart `Location.prototype.reload` override that only allows reloads triggered within 3s of user interaction (click/submit/keydown). Blocks HMR auto-reloads while preserving legitimate app reloads (Settings, PropertySwitcher, etc.)
  - **WebSocket keepalive:** HMR timeout reduced to 15s for more frequent pings, preventing proxy idle timeout.
  - **Regression tests:** 8 tests in `backend/tests/test_hmr_patch.py` covering patch existence, idempotency, config validation.
  - **Verified:** 2-minute Playwright stability test confirmed 0 auto-reloads, 1 suppressed attempt at ~60s mark.

## Phase A-I (COMPLETED)
All foundational layers: Notification, Auto-Action Engine, Unified Ops View, Control Plane, Channel Health, Drift Alerting, Import Bridge, Outbox Worker, ARI Push Engine, Crypto/Secrets modules.

## Decision-Driven UX Transformation (COMPLETED - March 2026)
### What was built:
1. **Dashboard Command Center** (`CommandCenter.jsx`):
   - Operational alerts ("Dikkat Gerektiren") with severity-based styling
   - Summary stat cards: Bugün Geliş, Bugün Çıkış, İçeride, Kirli Oda
   - Direct action navigation buttons per alert
   - Backend: `GET /api/pms/operational-alerts`

2. **Enhanced Room Board** (`RoomsTab.jsx`):
   - Live cleaning indicators for dirty rooms ("Temizlik bekliyor ~15 dk")
   - Animated progress bars for rooms being cleaned
   - Check-in ETA indicators for rooms with arrivals
   - Manrope font for room numbers
   - `DirtyRoomDecision` component with alternative room suggestions

3. **Upgraded Front Desk** (`FrontdeskTab.jsx`):
   - Enhanced arrival cards with guest name, room info, dates
   - Inline operational alerts (dirty room warning, balance)
   - VIP badge support
   - Departure cards with balance blocking check-out
   - Empty state messages for no arrivals/departures

4. **Smart Payment Dialog** (`PaymentDialog.jsx`):
   - Balance analysis bar (total, paid, remaining)
   - "Tüm bakiyeyi al" quick-fill button
   - Partial payment warnings
   - Gold-themed submit button

5. **Reservation Detail Ops Panel** (`ReservationDetailModal.jsx`):
   - Payment status indicator (pending/ok)
   - Room readiness indicator (dirty/cleaning/ready)
   - VIP/repeat guest badges
   - Guest preferences display

6. **Room Alternatives API** (`pms.py`):
   - `GET /api/pms/room-alternatives/{room_number}`
   - Returns same-type and different-type available rooms

## Key Endpoints
- `POST /api/auth/login` → `{access_token, user, tenant}`
- `GET /api/pms/operational-alerts` → `{alerts[], summary{}, available_clean_rooms[]}`
- `GET /api/pms/room-alternatives/{room_number}` → `{same_type[], other_type[]}`
- `GET /api/pms/dashboard` → room stats
- `GET /api/pms/rooms` → room list
- `GET /api/pms/bookings` → booking list

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Backlog (P1)
- Sandbox Simulation (Exely/HotelRunner) — duplicate delivery, delayed ack, retry storm, stale provider state
- SEC-001 Secrets Management — rotation + rollback plan
- SEC-002 Crypto Migration — dual-read / dual-write transition plan

## Backlog (P1.5)
- Alert → Business KPI Correlation — severity + runbook link + tenant/property/provider context

## Backlog (P2)
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
