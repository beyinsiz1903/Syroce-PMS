# Syroce PMS — Product Requirements Document

## Original Problem Statement
Hotel management platform (PMS) with channel manager integration (Exely, HotelRunner). Turkish-language interface.

### Key Feature: Toplu Güncellemeler (Bulk Updates)
HotelRunner-style bulk rate/availability management screen with:
- Per-room-type pricing toggle (per_person vs per_room)
- Independent rate plan selection per room type
- Calendar grid view
- Exely push integration

## Architecture
- **Frontend:** React + Shadcn UI + Tailwind CSS
- **Backend:** FastAPI + MongoDB
- **Integrations:** Exely (SOAP), HotelRunner (REST), Slack, Socket.IO

## What's Been Implemented

### Completed Features
1. **Toplu Güncellemeler Screen** — Bulk update UI with room types, rate plans, channels, date range, day selection
2. **Takvim Görünümü** — Calendar grid view for rates/availability
3. **Per-Room-Type Pricing Toggle** — Switch between per_person and per_room pricing for each room type
4. **Independent Room Type Selection (2026-03-18)** — Each room type has independent rate plan selection; clicking a room type header selects all its rate plans without affecting other room types
5. **Session & 404 Fixes (2026-03-18):**
   - Added catch-all route for unknown URLs → redirects to dashboard or auth
   - Fixed aggressive `localStorage.clear()` in handleLogin to only clear auth keys
   - Confirmed session persistence across multiple refreshes
6. **Exely Sync Fixes (2026-03-18):**
   - Batch pull now detects modifications via last_modify timestamp + guest_name/date comparison, even when Exely status is "commit"
   - Individual change checks limited to 30-day check-in window and batch size reduced from 50 to 20 for speed
7. **Unassigned Overlap Fix (2026-03-18):**
   - `getUnassignedBookingsForType` now filters by visible date range to avoid lane waste
   - Bookings starting before visible range now render from index 0 (left edge) instead of being hidden
   - Visible span calculation clamps to visible range boundaries

### Key Files
- `frontend/src/pages/RateManager.jsx` — Main rate manager UI
- `frontend/src/pages/ReservationCalendar.js` — Reservation calendar with unassigned overlap fix
- `frontend/src/App.js` — App routing, auth state, axios config, catch-all route
- `backend/domains/channel_manager/rate_manager_router.py` — Rate manager API
- `backend/domains/channel_manager/providers/exely/exely_pull_worker.py` — Exely sync with modification detection
- `backend/domains/channel_manager/providers/exely/auto_import.py` — Exely auto-import with cancellation handling
- `backend/domains/channel_manager/providers/common_ingest.py` — Idempotency guard and ingest pipeline
- `backend/core/security.py` — JWT auth, token creation/validation

### Key API Endpoints
- `GET /api/channel-manager/rate-manager/grid` — Rate calendar grid
- `POST /api/channel-manager/rate-manager/bulk-grid-update` — Bulk update (supports per-room-type selections)
- `GET /api/channel-manager/rate-manager/pricing-settings` — Get pricing settings
- `PUT /api/channel-manager/rate-manager/pricing-settings` — Update pricing settings
- `GET /api/auth/me` — Verify token and get current user
- `GET /api/subscription/current` — Get tenant subscription/modules
- `GET /api/pms/rooms` — Get rooms
- `GET /api/pms/bookings` — Get bookings

### DB Collections
- `rate_calendar` — Date-based rate/availability data
- `pricing_settings` — Per room type pricing model (per_person/per_room)
- `exely_reservations` — Exely reservation data with sync state
- `bookings` — PMS bookings

### Technical Notes
- **axios baseURL**: Emergent platform auto-appends `/api` to `REACT_APP_BACKEND_URL`. Relative axios calls (e.g., `/auth/me`) already route to `/api/auth/me`. DO NOT add `/api` prefix to relative calls.
- **JWT_SECRET**: Set in `backend/.env`. Token expiry: 168 hours (7 days).
- **Exely Pull Worker**: Runs every 30s, checks Exely SOAP API for new/modified/cancelled reservations.

## Pending Issues
- None critical. All P0-P2 issues resolved.

## Future Tasks (Priority Order)
1. **(P0) Narrow Rollout** — Execute narrow rollout with verified features
2. **(P1) Advanced Auto-Heal** — Enhance with confidence scores and provider-specific rules
3. **(P2) Deprecated Code Cleanup** — Remove old provider files (hotelrunner.py, client.py, exely_client_legacy.py)
4. **(P3) Core Lockdown Blocks B & C** — Finalize ProviderCapabilityMatrix and Reconciliation Truth Table
5. **(P4) Folio & Night Audit Hardening** — Harden financial modules
6. **(P4) Tenant Management** — Implement per-tenant rollout gates and feature flags

## Test Reports
- `/app/test_reports/iteration_84.json` — All tests passed (Backend 100%, Frontend 100%)

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
