# PMS + Channel Manager SaaS — PRD

## Problem Statement
Multi-tenant SaaS PMS with unified channel manager and robust polling/push webhook fallbacks. Hotels connect to OTAs (Booking.com, Expedia, EtsTur, JollyTur) via HotelRunner and Exely providers.

## Architecture
- **Frontend**: React (Vite) + Shadcn UI
- **Backend**: FastAPI + MongoDB
- **Integrations**: HotelRunner v2 (LIVE), Exely SOAP API, AWS KMS (encryption), Emergent LLM Key
- **Multi-tenancy**: Strict tenant isolation via `tenant_id` on all collections

## Completed Features
- Full PMS (rooms, bookings, calendar)
- HotelRunner v2 integration (polling + push)
- Exely SOAP integration (polling + auto-import)
- Unified Channel Connections dashboard (per-hotel credential management)
- **Role-based Channel Connections view** (2026-04-07):
  - Super admin: Full technical view with HotelRunner/Exely cards, credentials, management
  - Hotel users: Simplified view showing only connected OTA channel names
- Availability auto-sync & reconciliation workers
- Rate management (HotelRunner)
- Encryption layer for credentials
- Security: strawberry-graphql 0.312.3 (CVE-2026-35526, CVE-2026-35523 fixed), vite 8.0.5

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
