# PMS + Channel Manager SaaS — PRD

## Problem Statement
Multi-tenant SaaS PMS with unified channel manager and robust polling/push webhook fallbacks. Hotels connect to OTAs (Booking.com, Expedia, EtsTur, JollyTur) via HotelRunner and Exely providers.

## Architecture
- **Frontend**: React (Vite/CRA) + Shadcn UI
- **Backend**: FastAPI + MongoDB
- **Integrations**: HotelRunner v2 (LIVE), Exely SOAP API, AWS KMS (encryption), Emergent LLM Key
- **Multi-tenancy**: Strict tenant isolation via `tenant_id` on all collections

## Completed Features
- Full PMS (rooms, bookings, calendar)
- HotelRunner v2 integration (polling + push)
- Exely SOAP integration (polling + auto-import)
- Unified Channel Connections dashboard (per-hotel credential management)
- Availability auto-sync & reconciliation workers
- Rate management (HotelRunner)
- Encryption layer for credentials
- Security: strawberry-graphql upgraded to 0.312.3 (CVE-2026-35526, CVE-2026-35523 fixed)

## Backlog

### P1
- Auto Room Mapping Wizard

### P2
- Legacy HR Connector removal
- Real-time UI notifications for channel push results

### P3
- Channel Manager Dashboard (reservations, failed imports, push queue, health metrics)
- Admin UI Panel (encryption management)
- Calendar: make unassigned reservations more prominent
- Refactoring: hotelrunner_sync.py (~1000 lines), hr_rate_manager_router.py (~1100 lines)
