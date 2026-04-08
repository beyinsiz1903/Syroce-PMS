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
- **Admin Endpoints (Bearer Token Auth)**:
  - POST /api/b2b/api-keys — Create API key for agency
  - GET /api/b2b/api-keys/{agency_id} — Get key info
  - POST /api/b2b/api-keys/{agency_id}/regenerate — Regenerate key
  - DELETE /api/b2b/api-keys/{agency_id} — Revoke key
- **B2B Endpoints (X-API-Key Auth)**:
  - GET /api/b2b/content — Hotel content (room types, services)
  - GET /api/b2b/availability — Real-time room availability
  - GET /api/b2b/rates — Agency-specific or base rates
  - POST /api/b2b/reservations — Create reservation (auto PMS)
  - GET /api/b2b/reservations — List reservations
  - GET /api/b2b/reservations/{id} — Reservation detail
  - PUT /api/b2b/reservations/{id}/cancel — Cancel reservation
- Push providers endpoint includes Syroce B2B with active agency/key counts
- Test report: `/app/test_reports/iteration_196.json` - 100% pass (23/23 backend, all frontend)

## Pending / Known Issues
- P0: HotelRunner 429 Rate Limit (testing pending if timeout expired)

## Upcoming Tasks (P1)
- Retest HR Room Mapping Wizard after 429 timeout
- Real-time UI notifications for channel push results

## Future / Backlog (P2+)
- Channel Manager Dashboard (reservations, failed imports, push queue, health)
- Admin UI Panel for encryption management
- Make unassigned reservations more prominent in calendar
- Improve Auto Room Mapping (capacity + base price matching)
- Refactor: hotelrunner_sync.py (~1000 lines)
- Refactor: Evaluate deprecation of legacy hr_rate_manager_router.py and rate_manager_router.py
- Refactor: Migrate v1_ modules to v2 API
- B2B API Enhancement: Webhook system for reservation status changes
- B2B API Enhancement: API documentation page for agencies

## Key DB Collections
- `cm_connectors` — Encrypted channel credentials
- `hotel_content` — Agency data and rates mapping
- `users` — User accounts with roles
- `agency_api_keys` — B2B API keys (SHA256 hashed)
- `agency_rate_calendar` — Agency-specific rate data
- `agencies` — Agency profiles

## Key API Endpoints
- `GET /api/channel-manager/unified-rate-manager/grid`
- `GET /api/channel-manager/unified-rate-manager/push-providers`
- `GET /api/channel-manager/v2/mapping-wizard/{connector_id}/fetch-external`
- `GET /api/hotel-content` / `PUT /api/hotel-content`
- `GET /api/agencies`
- `POST /api/b2b/api-keys` / `GET /api/b2b/api-keys/{agency_id}`
- `GET /api/b2b/content` / `GET /api/b2b/availability` / `GET /api/b2b/rates`
- `POST /api/b2b/reservations` / `GET /api/b2b/reservations`
