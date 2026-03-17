# RoomOps PMS — Product Requirements Document

## Original Problem Statement
Build a production-grade hospitality platform (RoomOps PMS). Replace all mocked data provider integrations with real, robust, and maintainable API adapters.

## Core Requirements
1. **(P0 — DONE)** HotelRunner REST adapter — production-grade, 80+ tests
2. **(P0 — DONE)** Exely SOAP adapter — production-grade, 91+ tests
3. **(P0 — DONE)** Real Exely test environment integration — WSDL-based Security header, real API calls
4. **(P0 — DONE)** Calendar crash fix — TDZ error resolved
5. **(P0 — DONE)** Exely reservation pull — scheduler, vault, heartbeat, mappings fixed
6. **(P0 — DONE)** Fake reservation cleanup — all test/seed data removed (758 records)
7. **(P0 — DONE)** Exely → PMS Import endpoint — channel reservations can now be imported to PMS bookings
8. **(P1)** Mapping UI improvement — PMS room/rate <-> Provider room/rate mapping
9. **(P2)** Legacy collection cleanup — archive/delete unused DB collections

## Architecture
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React + Shadcn/UI
- **Providers**: HotelRunner (REST), Exely (SOAP/WCF)
- **Security**: Encrypted credential vault, JWT auth
- **Database**: hotel_pms (main), MongoDB

## Exely Real Test Environment
- **Endpoint**: `https://pmsconnect.test.hopenapi.com/Api/PMSConnect.svc`
- **HotelCode**: 501694
- **Property**: TEST Syroce PMS
- **Currency**: USD
- **Mode**: sandbox

### Discovered Inventory (Real)
| Room Types | Code | Name |
|---|---|---|
| 1 | 5001574 | Standart |
| 2 | 5001575 | Deluxe |
| 3 | 5001576 | Suite |

| Rate Plans | Code | Name |
|---|---|---|
| 1 | 10003182 | Best Day Price |
| 2 | 10003186 | Mixed rate USD |
| 3 | 10003541 | Dynamic Rate USD |
| 4 | 10003869 | Non-ref rate USD |
| 5 | 10003870 | Base rate USD |

## Exely → PMS Import Flow
1. Exely pull worker fetches reservations via OTA_ReadRQ → `exely_reservations` (pms_status: pending)
2. User clicks "PMS'e Aktar" on Exely Integration page
3. Backend `/api/channel-manager/exely/reservations/{id}/import`:
   - Maps room type via `exely_room_mappings` (5001574→Standard, 5001575→Deluxe, 5001576→Suite)
   - Creates guest in `guests` collection
   - Finds available room of matching type
   - Creates PMS booking in `bookings` collection
   - Updates channel reservation pms_status to "imported"

## Bug Fixes
- **(DONE - 2026-03-17)** ReservationCalendar crash: `isBlockStart` TDZ error
- **(DONE - prev session)** Global Axios error interceptor for Pydantic validation errors
- **(DONE - prev session)** Backend 500 on `/api/notifications/push-status` and `/api/hotel/team`

## Data Cleanup (2026-03-17)
- 758 fake records removed (bookings, guests, folios, test reservations, raw events)
- 30 rooms reset to "available" status
- Preserved: rooms, users, provider connections, mappings, tenant settings

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |

## Key API Endpoints
- `POST /api/channel-manager/exely/sync/reservations/pull` — Pull from Exely
- `GET /api/channel-manager/exely/reservations/local` — List channel reservations
- `POST /api/channel-manager/exely/reservations/{id}/import` — Import to PMS
- `GET /api/pms/bookings` — List PMS bookings
