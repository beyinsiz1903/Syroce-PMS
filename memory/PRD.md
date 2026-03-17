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
7. **(P0 — DONE)** Exely auto-import pipeline — Pull → Import → Booking+Guest+Room, fully automatic
8. **(P1)** Mapping UI improvement — PMS room/rate <-> Provider room/rate mapping
9. **(P2)** Legacy collection cleanup — archive/delete unused DB collections

## Architecture
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React + Shadcn/UI
- **Providers**: HotelRunner (REST), Exely (SOAP/WCF)
- **Database**: hotel_pms (main), MongoDB

## Exely Auto-Import Flow (DONE)
1. Backend startup → `ExelyPullScheduler.start(interval=10min)` auto-starts
2. Every 10 minutes: heartbeat → OTA_ReadRQ pull → `exely_reservations` (pending)
3. Auto-import: `auto_import_pending()` converts all pending → PMS bookings
4. Each import: maps room type, creates/finds guest, assigns available room, creates booking
5. Result: reservation visible in Bookings, Calendar, Dashboard, Guests

### Key Files
- `/app/backend/domains/channel_manager/providers/exely/auto_import.py` — Auto-import service
- `/app/backend/domains/channel_manager/providers/exely/exely_pull_worker.py` — Pull scheduler + auto-import integration
- `/app/backend/startup.py` — Auto-start scheduler on boot
- `/app/backend/domains/channel_manager/providers/exely/exely_router.py` — Manual pull/import endpoints
- `/app/backend/cache_warmer.py` — Fixed projection to include guest_name, source_channel

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

## Key API Endpoints
- `POST /api/channel-manager/exely/sync/reservations/pull` — Manual pull + auto-import
- `GET /api/channel-manager/exely/reservations/local` — List channel reservations
- `POST /api/channel-manager/exely/reservations/{id}/import` — Manual import fallback
- `GET /api/pms/bookings` — List PMS bookings (90-day range)

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
