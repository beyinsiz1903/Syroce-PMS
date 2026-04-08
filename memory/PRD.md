# Syroce PMS - Product Requirements Document

## Original Problem Statement
Multi-tenant SaaS PMS with unified channel manager. Build a unified Rate & Availability Manager ("Fiyat & Musaitlik") that handles both HotelRunner and Exely (depending on the active provider) and allows simultaneously pushing standard prices to channel managers and specific prices to selected local agencies from a single interface.

## User Language
Turkish (All responses must be in Turkish)

## Core Architecture
- Frontend: React (Vite) + Shadcn UI
- Backend: FastAPI + MongoDB
- Channel Integrations: HotelRunner v2 API, Exely SOAP API
- Encryption: AES-256-GCM for credentials

## What's Been Implemented

### Unified Rate Manager (DONE)
- Backend: `/app/backend/domains/channel_manager/unified_rate_manager_router.py`
- Frontend: `/app/frontend/src/pages/UnifiedRateManager.jsx`
- Auto-detects active provider (HR/Exely), agency pricing side-panel
- Legacy HR/Exely rate pages moved to "Teknik Yonetim" (super_admin only)

### Role-Based Delete Protection on Content Distribution (DONE - 2026-04-08)
- File: `/app/frontend/src/pages/AgencyContentDistribution.jsx`
- Receptionist/front_desk: Delete buttons completely hidden
- Admin/super_admin: AlertDialog confirmation before deletion
- Applies to both room types and services
- Test report: `/app/test_reports/iteration_195.json` - 100% pass

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

## Key DB Collections
- `cm_connectors` - Encrypted channel credentials
- `hotel_content` - Agency data and rates mapping
- `users` - User accounts with roles

## Key API Endpoints
- `GET /api/channel-manager/unified-rate-manager/grid`
- `GET /api/channel-manager/v2/mapping-wizard/{connector_id}/fetch-external`
- `GET /api/hotel-content`
- `PUT /api/hotel-content`
- `GET /api/agencies`
