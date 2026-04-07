# PMS + Channel Manager SaaS — PRD

## Problem Statement
Multi-tenant SaaS PMS with unified channel manager and robust polling/push webhook fallbacks. Hotels connect to OTAs (Booking.com, Expedia, EtsTur, JollyTur) via HotelRunner and Exely providers. Regional agencies without APIs are integrated via Agency Portal.

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
- CI/CD Docker build fix (removed --frozen-lockfile from Dockerfile)
- **Regional Agency Portal** (2026-04-07):
  - Agency CRUD (create/edit/delete agencies, manage users)
  - Agency user auth (JWT login via /agency-portal)
  - Availability search for agency users
  - Auto-drop reservations to PMS (no approval needed)
  - Hotel content management & distribution to agencies
  - Agency reservation tracking
  - Content Distribution page (hotel staff selects agencies, pushes content)
  - Agency Management page in PMS (under Kanallar nav group)
- **Auto Room Mapping Wizard** (2026-04-07):
  - 4-step wizard: Kanal Secimi -> Oda Eslestirme -> Fiyat Plani -> Onay & Kayit
  - Fuzzy name matching (difflib.SequenceMatcher + Turkish/English alias boosting)
  - Confidence scores per suggestion (auto >=60%, review <60%)
  - Greedy optimal matching to prevent duplicate external entity assignments
  - Bulk-create confirmed mappings
  - Rate plan suggestions (same fuzzy matching)
  - Existing mappings shown separately
  - Accessible via Kanallar menu -> "Oda Eslestirme Sihirbazi"

## Backlog

### P2
- Legacy HR Connector removal
- Real-time UI notifications for channel push results

### P3
- Channel Manager Dashboard (reservations, failed imports, push queue, health metrics)
- Admin UI Panel (encryption management)
- Calendar: make unassigned reservations more prominent
- Refactoring: hotelrunner_sync.py (~1000 lines), hr_rate_manager_router.py (~1100 lines)
