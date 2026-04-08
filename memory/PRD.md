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
- Backend: `/app/backend/domains/channel_manager/unified_rate_manager_router.py`
- Frontend: `/app/frontend/src/pages/UnifiedRateManager.jsx`
- Auto-detects active provider (HR/Exely), agency pricing side-panel
- Push providers: HotelRunner, Exely, Syroce B2B

### Role-Based Delete Protection on Content Distribution (DONE - 2026-04-08)
- File: `/app/frontend/src/pages/AgencyContentDistribution.jsx`
- Receptionist/front_desk: Delete buttons hidden
- Admin/super_admin: AlertDialog confirmation before deletion

### Syroce B2B API (DONE - 2026-04-08)
- Backend: `/app/backend/routers/b2b_api.py`
- Frontend: `/app/frontend/src/pages/AgencyManagement.jsx` (API Key management UI)
- Admin + B2B Endpoints

### B2B API Documentation Page (DONE - 2026-04-08)
- Frontend: `/app/frontend/src/pages/B2BApiDocs.jsx`
- Route: `/b2b/docs` (public, no auth required, standalone layout)

### Webhook System (DONE - 2026-04-08)
- Backend: `/app/backend/routers/b2b_api.py` (webhook endpoints)
- Events: reservation.created, reservation.cancelled, reservation.updated

### Deployment Fixes (DONE - 2026-04-08)
- `.gitignore` cleaned (1553 → 83 lines)
- CORS: Added production domain
- Import sorting fixed in `b2b_api.py`

### CI Test Fixes — TenantViolationError (DONE - 2026-04-09)
- Fixed 18 FAILED + 10 ERROR tests caused by `STRICT_TENANT_MODE=true`
- **Root causes & fixes:**
  - `tests/resilience/conftest.py`: `db` fixture now returns `_raw_db` (bypasses TenantAwareDBProxy); cleanup uses `_raw_db` directly
  - `tests/battle/test_sprint2_hold_ooo.py`: Cleanup uses `raw_db`; test body gets `set_tenant_context(TENANT_ID)` via fixture
  - `tests/resilience/test_provider_failures.py`: `_handle_import_failure` call wrapped with `tenant_context()`
  - `controlplane/alerting.py` (APP BUG): `AlertingEngine._get_db()` now uses `get_system_db()` instead of proxy (cross-tenant system operation)
- **Trivy CVE-2026-35030**: Added `.trivyignore` (litellm used as client, not proxy; upgrade blocked by emergentintegrations pinning openai==1.99.9)

### RMS Module — Backend Endpoint Fixes (DONE - 2026-04-08)
- Removed 5 simplified duplicate endpoints from `enterprise_router.py` that were overriding enhanced `rms_router.py` versions
- Added `GET /rms/pricing-strategy` — computes current ADR from bookings, recommended from ML, market position from comp-set
- Added `PUT /rms/pricing-strategy` — updates auto_pricing_enabled in DB
- Added `GET /rms/price-adjustments` — returns applied recommendations history
- Added `POST /rms/apply-recommendations` — applies all pending pricing recommendations with audit trail
- Enhanced `GET /rms/demand-forecast` — now supports `days` param, generates forecasts from live booking data
- Enhanced `GET /rms/comp-set` — enriches competitors with avg_rate, occupancy_rate, revpar from comp_pricing

### Advanced Menu Icon Fix (DONE - 2026-04-08)
- Added unique icons for 5 modules that had generic Home fallback icons
- Data Intelligence → BrainCircuit, Messaging Center → MessageSquare, ML Scheduler → Clock, Revenue Autopilot → Rocket, Analytics Export → Download

## Pending / Known Issues
- litellm CVE-2026-35030: Suppressed in `.trivyignore`. Upgrade to >=1.83.0 blocked by emergentintegrations dependency chain (openai==1.99.9 vs openai>=2.8.0). Monitor emergentintegrations releases.

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

## Key DB Collections
- `cm_connectors` — Encrypted channel credentials
- `hotel_content` — Agency data and rates mapping
- `users` — User accounts with roles
- `agency_api_keys` — B2B API keys (SHA256 hashed)
- `agency_rate_calendar` — Agency-specific rate data
- `agencies` — Agency profiles
- `agency_webhooks` — Webhook registrations
- `webhook_deliveries` — Webhook delivery logs

## Key API Endpoints
- `GET /api/channel-manager/unified-rate-manager/grid`
- `GET /api/channel-manager/unified-rate-manager/push-providers`
- `POST /api/b2b/api-keys` / `GET /api/b2b/api-keys/{agency_id}`
- `GET /api/b2b/content` / `GET /api/b2b/availability` / `GET /api/b2b/rates`
- `POST /api/b2b/reservations` / `GET /api/b2b/reservations`
- `POST /api/b2b/webhooks` / `GET /api/b2b/webhooks` / `DELETE /api/b2b/webhooks/{id}`
