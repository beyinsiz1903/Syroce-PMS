# RoomOps PMS — Product Requirements Document

## Original Problem Statement
Build a production-grade hospitality platform (RoomOps PMS). Replace all mocked data provider integrations with real, robust, and maintainable API adapters.

## Core Requirements
1. **(P0 — DONE)** HotelRunner REST adapter
2. **(P0 — DONE)** Exely SOAP adapter
3. **(P0 — DONE)** Real Exely test environment integration
4. **(P0 — DONE)** Calendar crash fix — TDZ error resolved
5. **(P0 — DONE)** Exely reservation pull — scheduler, vault, heartbeat, mappings
6. **(P0 — DONE)** Fake reservation cleanup — 758 records removed
7. **(P0 — DONE)** Exely auto-import pipeline — Pull → Import → Booking+Guest+Room, fully automatic (interval: 60s)
8. **(P0 — DONE)** Reservation notification — auto-creates bell notification when new Exely booking is imported
9. **(P0 — DONE)** Rate Manager — Fiyat/Müsaitlik/Min Konaklama/Stop-sell yönetimi, Exely push ile
10. **(P1)** Mapping UI improvement — PMS room/rate <-> Provider room/rate mapping
11. **(P2)** Legacy collection cleanup — archive/delete unused DB collections

## Architecture
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React + Shadcn/UI
- **Providers**: HotelRunner (REST), Exely (SOAP/WCF)
- **Database**: hotel_pms (main), MongoDB

## Exely Auto-Import Flow (DONE)
1. Backend startup → `ExelyPullScheduler.start(interval_seconds=60)` auto-starts
2. Every 60 seconds: heartbeat → OTA_ReadRQ pull → `exely_reservations` (pending)
3. Auto-import: `auto_import_pending()` converts all pending → PMS bookings
4. Each import: maps room type, creates/finds guest, assigns available room, creates booking
5. Notification auto-created for each imported booking (shown in bell icon)
6. Result: reservation visible in Bookings, Calendar, Dashboard, Guests + notification

## Rate Manager Flow (DONE)
1. User opens /rate-manager page
2. Grid shows room types × rate plans × dates (14-day view, navigable)
3. Click any cell → edit dialog: fiyat, müsaitlik, min konaklama, satış durdur
4. Save → `rate_calendar` collection updated + `ExelyProvider.push_ari()` SOAP call
5. Exely receives update → distributes to connected OTAs

### Rate Manager API Endpoints
- `GET /api/channel-manager/rate-manager/grid` — Date range grid (room type × rate plan × date)
- `POST /api/channel-manager/rate-manager/update` — Save + push to Exely
- `GET /api/channel-manager/rate-manager/room-types` — Available room types and rate plans

### Key Files
- `/app/backend/domains/channel_manager/rate_manager_router.py` — Rate Manager API
- `/app/frontend/src/pages/RateManager.jsx` — Rate Manager UI
- `/app/backend/domains/channel_manager/providers/exely/auto_import.py` — Auto-import + notification
- `/app/backend/domains/channel_manager/providers/exely/exely_pull_worker.py` — Pull scheduler
- `/app/backend/startup.py` — Auto-start scheduler on boot
- `/app/frontend/src/components/NotificationBell.js` — Bell notification component (fixed API URLs)

## Exely Real Test Environment
- **Endpoint**: `https://pmsconnect.test.hopenapi.com/Api/PMSConnect.svc`
- **HotelCode**: 501694
- **Property**: TEST Syroce PMS

### Room Type Mapping
| Exely Code | Exely Name | PMS Room Type |
|---|---|---|
| 5001574 | Standart | Standard |
| 5001575 | Deluxe | Deluxe |
| 5001576 | Suite | Suite |

### Rate Plans
| Code | Name |
|---|---|
| 10003870 | Base rate USD |
| 10003869 | Non-ref rate USD |
| 10003541 | Dynamic Rate USD |
| 10003186 | Mixed rate USD |
| 10003182 | Лучшая цена дня |

## Key API Endpoints
- `POST /api/channel-manager/exely/sync/reservations/pull` — Manual pull + auto-import
- `GET /api/channel-manager/exely/reservations/local` — List channel reservations
- `GET /api/pms/bookings` — List PMS bookings (90-day range)
- `GET /api/notifications/list` — User notifications
- `PUT /api/notifications/{id}/mark-read` — Mark notification as read

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
