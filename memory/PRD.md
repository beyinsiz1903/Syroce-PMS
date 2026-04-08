# Syroce PMS - Product Requirements Document

## Original Problem Statement
Multi-tenant SaaS PMS with unified channel manager. Build a unified Rate & Availability Manager that handles both HotelRunner and Exely. Syroce B2B API infrastructure for agency automation system integration — agencies can authenticate via API key and access hotel content, availability, rates, create/manage reservations through the same channel manager architecture.

## User Language
Turkish (All responses must be in Turkish)

## Core Architecture
- Frontend: React (Vite) + Shadcn UI
- Backend: FastAPI + MongoDB
- Channel Integrations: HotelRunner v2 API, Exely SOAP API, Syroce B2B API
- Encryption: AES-256-GCM for credentials
- B2B Auth: API Key (SHA256 hashed, X-API-Key header)
- Tenant Isolation: TenantAwareDBProxy with STRICT_TENANT_MODE=true

## What's Been Implemented

### Unified Rate Manager (DONE)
### Role-Based Delete Protection on Content Distribution (DONE - 2026-04-08)
### Syroce B2B API (DONE - 2026-04-08)
### B2B API Documentation Page (DONE - 2026-04-08)
### Webhook System (DONE - 2026-04-08)
### Deployment Fixes (DONE - 2026-04-08)
### CI Test Fixes — TenantViolationError (DONE - 2026-04-09)
### RMS Module — Backend Endpoint Fixes (DONE - 2026-04-08)
### Advanced Menu Icon Fix (DONE - 2026-04-08)
### Advanced Module Consolidation (DONE - 2026-04-08)

### RMS Module — Complete Rewrite to Internal-Data-Driven System (DONE - 2026-04-08)
- **Motivation**: User decided not to rely on competitor pricing (web scraping is fragile, OTA rate shopping services cost $75-400/mo). RMS now uses only internal hotel data.
- **7-Factor Pricing Algorithm**:
  1. Doluluk Orani (Occupancy) — 25% weight
  2. Rezervasyon Hizi / Pickup — 20% weight
  3. Lead Time (Days to arrival) — 15% weight
  4. Haftanin Gunu & Mevsimsellik — 15% weight
  5. Iptal Orani (Cancellation Rate) — 10% weight
  6. Kanal Bazli Performans (Channel Performance) — 10% weight
  7. Gecmis Yil Karsilastirma (YoY) — 5% weight
- **New Backend Endpoints**:
  - `GET /api/rms/dashboard-kpis` — Comprehensive KPIs (doluluk, ADR, RevPAR, pickup, cancel rate, channels, daily trend)
  - `POST /api/rms/generate-pricing` — New 7-factor pricing engine
  - `GET/POST/PUT/DELETE /api/rms/yield-rules` — Yield rules CRUD
  - `GET/POST/PUT/DELETE /api/rms/seasonal-calendar` — Seasonal calendar CRUD
  - `GET /api/rms/channel-performance` — Monthly channel breakdown
- **New Frontend Components**:
  - `RMSModule.jsx` — Complete rewrite: KPI cards (TRY), doluluk trendi chart, kanal dagilimi doughnut, oda tipi performansi bar chart, fiyat onerileri table, kanal detay tablosu
  - `YieldRulesPanel.jsx` — Yield rules CRUD UI with priority, conditions, actions
  - `SeasonCalendarPanel.jsx` — Seasonal calendar with visual timeline + CRUD
  - `GelirYonetimiPage.jsx` — 4 tabs: Dashboard, Yield Kurallari, Sezon Takvimi, Autopilot
- **Seed Data**: auto_seed.py updated with:
  - TRY prices (Standard: 4500, Deluxe: 6800, Superior: 9200, Suite: 14000)
  - 265 bookings (6 months history with channel distribution)
  - 6 room types, 5 yield rules, 6 seasonal calendar entries
- **Test Result**: Backend 16/16, Frontend 100% — iteration_200.json

### Messaging Dashboard Layout Fix (DONE - 2026-04-08)
- Fixed missing Layout wrapper on MessagingDashboard — top navigation was disappearing when navigating to `/messaging-dashboard`
- Wrapped component in `<Layout>` to match other consolidated page patterns

## Pending / Known Issues
- litellm CVE-2026-35030: Suppressed in `.trivyignore`. Upgrade to >=1.83.0 blocked by emergentintegrations dependency chain.

## Upcoming Tasks (P1)
- Real-time UI notifications for channel push results

## Future / Backlog (P2+)
- Automatic retry mechanism with exponential backoff for failed webhook deliveries
- B2B Analytics Dashboard (agency API key usage, booking rates, top queries)
- Channel Manager Dashboard (reservations, failed imports, push queue, health)
- Admin UI Panel for encryption management
- Make unassigned reservations more prominent in calendar
- Improve Auto Room Mapping (capacity + base price matching)
- Refactor: hotelrunner_sync.py (~1000 lines)
- Refactor: Evaluate deprecation of legacy hr_rate_manager_router.py and rate_manager_router.py
- Real competitor price integration via SerpApi or OTA Insight (when budget allows)

## Key DB Collections
- `cm_connectors` — Encrypted channel credentials
- `hotel_content` — Agency data and rates mapping
- `users` — User accounts with roles
- `agency_api_keys` — B2B API keys (SHA256 hashed)
- `agency_rate_calendar` — Agency-specific rate data
- `room_types` — Room type definitions with TRY base/min/max rates
- `yield_rules` — Automatic pricing rules (condition-action pairs)
- `seasonal_calendar` — Season definitions with rate multipliers
- `rms_pricing_recommendations` — Generated pricing recommendations
- `bookings` — Reservations with channel, room_type, base_rate fields

## Key API Endpoints
- `GET /api/channel-manager/unified-rate-manager/grid`
- `GET /api/channel-manager/unified-rate-manager/push-providers`
- `POST /api/b2b/api-keys` / `GET /api/b2b/api-keys/{agency_id}`
- `GET /api/b2b/content` / `GET /api/b2b/availability` / `GET /api/b2b/rates`
- `POST /api/b2b/reservations` / `GET /api/b2b/reservations`
- `POST /api/b2b/webhooks` / `GET /api/b2b/webhooks` / `DELETE /api/b2b/webhooks/{id}`
- `GET /api/rms/dashboard-kpis` / `GET /api/rms/channel-performance`
- `POST /api/rms/generate-pricing` / `POST /api/rms/apply-recommendations`
- `GET/POST/PUT/DELETE /api/rms/yield-rules`
- `GET/POST/PUT/DELETE /api/rms/seasonal-calendar`
