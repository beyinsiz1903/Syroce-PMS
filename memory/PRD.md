# Syroce PMS — Product Requirements Document

## Original Problem Statement
Multi-tenant SaaS PMS with unified channel manager. Real HotelRunner API integration (not mock data), credential management via encrypted vault, and production-ready channel sync.

## User Personas
- **Hotel Admin (super_admin):** Full access to all features including technical ops panels
- **Front Desk Staff (front_desk):** Operational access — daily tasks, reservations, basic channel management
- **Guest:** Self-service portal for bookings and profile

## Core Architecture
- **Frontend:** React (Vite) + Shadcn UI + Tailwind CSS
- **Backend:** FastAPI + MongoDB
- **Integrations:** HotelRunner v2, Exely (SOAP), AWS KMS encryption, Emergent LLM

## What's Been Implemented

### Unified Rate & Availability Manager (2026-04-07)
- Single "Fiyat & Musaitlik" page replacing separate HR/Exely rate managers
- Auto-detects active channel provider (HotelRunner or Exely)
- Unified grid, bulk update, and stop sale tabs
- Agency panel: select agencies to receive rate/availability updates
- Agency-specific rate overrides (multiplier or fixed rate)
- When updating, pushes to active channel provider + selected agencies
- Old HR/Exely rate pages preserved under Teknik Yonetim for admins
- Key endpoints:
  - `GET /api/channel-manager/unified-rate-manager/detect-provider`
  - `GET /api/channel-manager/unified-rate-manager/grid`
  - `POST /api/channel-manager/unified-rate-manager/bulk-grid-update`
  - `GET /api/channel-manager/unified-rate-manager/agencies`
  - `POST /api/channel-manager/unified-rate-manager/agency-rates`
- Data collections: `agency_rate_calendar`, `agency_rate_overrides`

### Channel Manager
- Unified Channel Manager with HotelRunner + Exely integration
- Room mapping wizard with auto-suggestion (fuzzy matching)
- ARI Push Engine for availability/rate/inventory sync
- Wire Failure tracking dashboard
- Lockdown Dashboard, Incident Panel, Runtime Cockpit
- Control Plane with event timeline
- Data Model visualization
- Integration Hub
- Admin Control Panel (20 tabs)
- Rate managers for both HR and Exely (now under Teknik Yonetim)
- Agency management + content distribution

### Navigation Restructure (2026-04-07)
- Kanallar menu simplified to 2-tier structure
- Normal users see: Channel Manager, Fiyat & Musaitlik, Oda Eslestirme, Acente Yonetimi, Icerik Dagitimi
- Admin sees additional items under "Teknik Yonetim" separator (including old HR/Exely rate pages)

### Credential Management
- Real HotelRunner credentials extracted from DB, encrypted with AES-256-GCM
- Stored in cm_connectors collection
- Dynamic environment detection (sandbox vs production)

### Background Workers
- HR Pull Scheduler: 300s interval (was 30s, caused rate limiting)
- Exely Pull Scheduler: 30s interval
- Dashboard snapshot: 60s
- Room-type inventory: 300s
- Availability reconciliation: 900s

## Prioritized Backlog

### P0
- HotelRunner 429 Rate Limit recovery — verify when rate limit resets

### P2
- Real-time UI notifications for channel push results

### P3 (Future)
- Channel Manager Dashboard (reservations, failed imports, push queue, connection health)
- Admin UI Panel for encryption management
- Make unassigned reservations more prominent in calendar
- Improve Auto Room Mapping (capacity + base price matching)

### Refactoring
- `hotelrunner_sync.py` (~1000 lines) — split Phase A/B logic
- `hr_rate_manager_router.py` (>1100 lines)
- Migrate `v1_` modules to v2 API format

## Key Collections
- `cm_connectors` — encrypted channel credentials
- `agency_rate_calendar` — agency rate/availability data (NEW)
- `agency_rate_overrides` — agency-specific rate overrides (NEW)
- `provider_secrets` / `_dev_secrets` — legacy secret stores
- `hotelrunner_pull_cursors` — sync cursor tracking
- `webhook_raw_payloads` — raw webhook storage

## 3rd Party Integrations
- AWS KMS (AES-256-GCM encryption)
- HotelRunner v2 REST API
- Exely SOAP API
- Emergent LLM (AI features)
