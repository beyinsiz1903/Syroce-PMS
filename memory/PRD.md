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

### B2B API Documentation Page (DONE - 2026-04-08)
- Frontend: `/app/frontend/src/pages/B2BApiDocs.jsx`
- Route: `/b2b/docs` (public, no auth required, standalone layout)
- EN/TR language toggle at top-right
- Sections: Overview, Authentication, Content, Availability, Rates, Reservations, Webhooks
- Modern API docs design with dark code blocks, method badges, parameter tables
- Agency Management page has "API Docs Linki Kopyala" button

### Webhook System (DONE - 2026-04-08)
- Backend: `/app/backend/routers/b2b_api.py` (webhook endpoints)
- **Webhook Endpoints (X-API-Key Auth)**:
  - POST /api/b2b/webhooks — Register webhook URL
  - GET /api/b2b/webhooks — List webhooks
  - DELETE /api/b2b/webhooks/{webhook_id} — Delete webhook
  - POST /api/b2b/webhooks/{webhook_id}/test — Send test event
- Events: reservation.created, reservation.cancelled, reservation.updated
- Auto-fire: Webhooks triggered via BackgroundTasks on reservation create/cancel
- HMAC-SHA256 signature verification support
- Max 5 active webhooks per agency, HTTPS-only URLs
- DB: `agency_webhooks`, `webhook_deliveries` collections
- Test report: `/app/test_reports/iteration_197.json` - 100% pass

## Pending / Known Issues
- P0: HotelRunner 429 Rate Limit (testing pending if timeout expired)

## Upcoming Tasks (P1)
- Retest HR Room Mapping Wizard after 429 timeout
- Real-time UI notifications for channel push results

## Future / Backlog (P2+)
- B2B Analytics Dashboard (agency API key usage, booking rates, top queries)
- Channel Manager Dashboard (reservations, failed imports, push queue, health)
- Admin UI Panel for encryption management
- Make unassigned reservations more prominent in calendar
- Improve Auto Room Mapping (capacity + base price matching)
- Refactor: hotelrunner_sync.py (~1000 lines)
- Refactor: Evaluate deprecation of legacy hr_rate_manager_router.py and rate_manager_router.py
- Refactor: Migrate v1_ modules to v2 API

## Key DB Collections
- `cm_connectors` — Encrypted channel credentials
- `hotel_content` — Agency data and rates mapping
- `users` — User accounts with roles
- `agency_api_keys` — B2B API keys (SHA256 hashed)
- `agency_rate_calendar` — Agency-specific rate data
- `agencies` — Agency profiles
- `agency_webhooks` — Webhook registrations (url, events, secret, is_active)
- `webhook_deliveries` — Webhook delivery logs (status_code, error, event)

## Key API Endpoints
- `GET /api/channel-manager/unified-rate-manager/grid`
- `GET /api/channel-manager/unified-rate-manager/push-providers`
- `GET /api/channel-manager/v2/mapping-wizard/{connector_id}/fetch-external`
- `GET /api/hotel-content` / `PUT /api/hotel-content`
- `GET /api/agencies`
- `POST /api/b2b/api-keys` / `GET /api/b2b/api-keys/{agency_id}`
- `GET /api/b2b/content` / `GET /api/b2b/availability` / `GET /api/b2b/rates`
- `POST /api/b2b/reservations` / `GET /api/b2b/reservations`
- `POST /api/b2b/webhooks` / `GET /api/b2b/webhooks` / `DELETE /api/b2b/webhooks/{id}`
- `POST /api/b2b/webhooks/{id}/test`
