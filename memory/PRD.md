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
- Rate managers for both HR and Exely
- Agency management + content distribution

### Navigation Restructure (2026-04-07)
- Kanallar menu simplified from 18 items to 2-tier structure
- Normal users see 6 items: Channel Manager, HR/Exely Fiyat, Oda Eslestirme, Acente, Icerik Dagitimi
- Admin (super_admin) sees additional 12 items under "Teknik Yonetim" separator

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
- HotelRunner 429 Rate Limit recovery — verify when rate limit resets, test mapping wizard end-to-end

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

## Key Endpoints
- `GET /api/channel-manager/v2/mapping-wizard/{connector_id}/fetch-external`
- `POST /api/channel-manager/hotelrunner/sync/scheduler/stop`
- `GET /api/channel-manager/connections/overview`
- `GET /api/channel-manager/hr-rate-manager/grid`
- `GET /api/channel-manager/wire-failures/summary`

## Key Collections
- `cm_connectors` — encrypted channel credentials
- `provider_secrets` / `_dev_secrets` — legacy secret stores
- `hotelrunner_pull_cursors` — sync cursor tracking
- `webhook_raw_payloads` — raw webhook storage

## 3rd Party Integrations
- AWS KMS (AES-256-GCM encryption)
- HotelRunner v2 REST API
- Exely SOAP API
- Emergent LLM (AI features)
