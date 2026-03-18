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

### Key Files
- `frontend/src/pages/RateManager.jsx` — Main rate manager UI
- `backend/domains/channel_manager/rate_manager_router.py` — Rate manager API

### Key API Endpoints
- `GET /api/channel-manager/rate-manager/grid` — Rate calendar grid
- `POST /api/channel-manager/rate-manager/bulk-grid-update` — Bulk update (supports per-room-type selections)
- `GET /api/channel-manager/rate-manager/pricing-settings` — Get pricing settings
- `PUT /api/channel-manager/rate-manager/pricing-settings` — Update pricing settings

### DB Collections
- `rate_calendar` — Date-based rate/availability data
- `pricing_settings` — Per room type pricing model (per_person/per_room)

## Pending Issues
- P1: Exely sync bug fixes (name/date changes, cancellation speed)
- P2: "Unassigned Overlap" in calendar view
- P3: Session logouts and 404 errors

## Future Tasks
- Narrow Rollout execution
- Advanced Auto-Heal
- Deprecated code cleanup
- ProviderCapabilityMatrix & Reconciliation Truth Table
- Folio & Night Audit hardening
- Tenant management & feature flags

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
