# Syroce PMS - Product Requirements Document

## Original Problem Statement
Otel Yonetim Sistemi (Syroce PMS) - 5 yildizli otel operasyonlari icin kapsamli PMS cozumu.

## Architecture
- **Frontend:** React, Tailwind CSS, Shadcn UI, Recharts, i18next, jspdf
- **Backend:** FastAPI, MongoDB (motor), JWT auth, openpyxl, WeasyPrint
- **Database:** MongoDB with tenant isolation

## Implemented Features

### Phase 1-3 (Previously Completed)
- Full PMS, Dashboard, Housekeeping, Finance, Channel Manager, RMS, AI, Multi-property, Night Audit, Mobile views

### Phase 4: Reporting & Analytics (COMPLETED)
- Custom Report Builder, Excel & PDF Export

### Phase 5: Guest Portal & Communication (COMPLETED)
- Guest Messaging System (backend + frontend)

### Phase 7: Security & Performance (COMPLETED - Feb 2026)
- Security Headers, JWT Refresh, Audit Logging, Security Dashboard

### i18n Internationalization (COMPLETED - Feb 2026)
- 1816 t() calls, 1334 keys, 48 sections, 8 languages
- HousekeepingDetailedReports.js fully converted with 35+ new keys

### PMSModule.js Refactoring (COMPLETED - Feb 2026)
- 5189 -> 2985 lines, 12 extracted components

### Load Testing & Performance Optimization (COMPLETED - Feb 2026)
- Locust 2.43.3: 50 concurrent users, 120s, 4 roles, 34 endpoints
- Login -74.5%, Forecast -99.3%, Overall avg -33.5%, p99 -52.1%

### server.py Modularization - Phase 1 (COMPLETED - Feb 2026)
- **Extracted 3 routers:** auth.py (668 lines), housekeeping.py (750 lines), departments.py (2986 lines)
- **Reduced server.py:** 55,671 -> 51,409 lines (-4,262 lines, -7.7%)
- **Created core/helpers.py:** Shared utilities

### server.py Modularization - Phase 2 (COMPLETED - Feb 2026)
- **Extracted 3 more routers:** pms.py (2,771 lines, 52 routes), finance.py (4,627 lines, 90 routes), reports.py (1,822 lines, 28 routes)
- **Created core/utils.py:** Shared utility functions (folio helpers, Excel helpers, QR code, night audit helpers)
- **Removed 26 duplicate route definitions** (OPERA CLOUD PARITY duplicates)
- **Fixed route conflicts:** Removed mock night-audit endpoints from comprehensive_modules_endpoints.py
- **Reduced server.py:** 51,409 -> 41,622 lines (-9,787 lines, -19%)
- **Total reduction from original:** 55,671 -> 41,622 (-14,049 lines, -25.2%)
- **All 59 endpoint tests pass (100%)**

### Calendar Drag-Drop Room Move Bug Fix (COMPLETED - Mar 2026)
- **Bug:** Other reservations disappearing after drag-drop room change
- **Root causes:** (1) `setCurrentDate(newCheckIn)` shifted calendar view causing bookings to go out of visible range, (2) Stale setTimeout closure, (3) room_number not updated in DB after room_id change, (4) cached GET path not enriching room_number
- **Fixes:** Replaced `setCurrentDate` with direct `loadCalendarData()` call (view stays put), cleaned PUT payload to send only changed fields, backend syncs room_number on room move, GET always re-enriches room_number
- **Tests:** 8/8 backend tests pass (test_booking_room_move_fix.py)

### Calendar Sidebar Action Buttons Fix (COMPLETED - Mar 2026)
- **Bug:** View Folio, Edit Reservation, Send Confirmation buttons in booking sidebar did nothing
- **Root cause:** Parent component didn't pass callback functions (`onViewFolio`, `onEditReservation`, `onSendConfirmation`) to `ReservationSidebar`
- **Fix:** Implemented 3 handler functions in ReservationCalendar.js and wired them to the sidebar component
  - View Full Folio → navigates to /invoices (Fatura & Finans)
  - Edit Reservation → navigates to /pms#bookings
  - Send Confirmation → calls WhatsApp API with toast feedback

### Semantic Migration Sprint 1 Foundations (COMPLETED - Mar 2026)
- **Created semantic module skeletons:** `backend/modules/reservations`, `stays`, `inventory`, `folio`
- **Created shared kernel primitives:** `backend/shared_kernel/tenancy_context.py`, `event_envelope.py`, `audit_helper.py`, `idempotency.py`
- **Added governance:** `server.py` now contains explicit no-new-business-logic rule; semantic extraction ADR created at `backend/SEMANTIC_EXTRACTION_ADR.md`
- **Started read-side abstraction:** added reservation, stay, availability, and folio balance read services
- **Bridged low-risk read paths:** `GET /api/pms/bookings`, `GET /api/pms/rooms/availability`, `GET /api/folio/{folio_id}` now delegate to semantic read services without changing external contracts
- **Testing:** backend regression smoke passed; frontend smoke passed; new foundation tests added under `backend/tests/`

### Root Directory Cleanup (COMPLETED - Feb 2026)
- Removed 152 test .py files from root directory
- Clean project structure

## Code Architecture
```
/app
├── backend/
│   ├── server.py              # Main server (41,622 lines)
│   ├── modules/               # Semantic migration foundations (NEW)
│   │   ├── reservations/      # Reservation read abstraction + future write migration
│   │   ├── stays/             # Stay aggregate read abstraction + future write migration
│   │   ├── inventory/         # Availability read abstraction + future inventory migration
│   │   └── folio/             # Folio balance/detail read abstraction + future finance migration
│   ├── shared_kernel/         # Tenant/event/audit/idempotency primitives (NEW)
│   ├── core/
│   │   ├── database.py        # MongoDB connection
│   │   ├── security.py        # JWT auth, password hashing
│   │   ├── helpers.py         # Shared helpers (tenant, modules, audit)
│   │   ├── utils.py           # Shared utilities (NEW - folio, excel, QR, night audit)
│   │   └── sanitize.py        # Input sanitization
│   ├── routers/
│   │   ├── auth.py            # Auth endpoints (668 lines)
│   │   ├── housekeeping.py    # Housekeeping endpoints (750 lines)
│   │   ├── departments.py     # Department dashboards (2,986 lines)
│   │   ├── pms.py             # PMS/Rooms/Bookings (NEW - 2,771 lines, 52 routes)
│   │   ├── finance.py         # Finance/Accounting/Folio (NEW - 4,627 lines, 90 routes)
│   │   ├── reports.py         # Reports/Night Audit (NEW - 1,822 lines, 28 routes)
│   │   ├── report_builder.py  # Report builder
│   │   └── guest_messaging.py # Guest messaging
│   ├── models/
│   │   ├── enums.py           # Enumerations
│   │   └── schemas.py         # Pydantic models
│   └── tests/
│       ├── test_pms_finance_reports_routers.py  # (NEW)
│       └── test_router_modularization.py        # (NEW)
│       ├── test_semantic_migration_foundations.py # Sprint 1 foundation tests (NEW)
│       └── harnesses/         # Contract + tenant isolation test harnesses (NEW)
├── frontend/
│   └── src/
│       ├── locales/           # i18n files
│       ├── components/
│       │   ├── pms/           # PMS sub-components
│       │   └── ui/            # Shadcn UI
│       └── pages/             # Route pages
└── memory/
    └── PRD.md
```

### Full E2E Testing & Fixes (COMPLETED - Mar 2026)
- **Scope:** 16 pages tested end-to-end - ALL pass without white screens or errors
- **Pages verified:** Dashboard, Calendar, PMS (6 tabs), Reports, Settings, Fatura & Finans (6 tabs), Maliyet, Channel Manager, Gelişmiş Raporlar, Rapor Oluşturucu, RMS, Group Reservations, E-Fatura, Sales, Maintenance, OTA Messaging
- **Fixes applied:**
  - Rate limiting: Increased default from 120→300 req/min, reports 30→60, whitelisted common GET endpoints
  - Occupancy report: Fixed timezone-aware vs naive datetime comparison causing 500 errors

## Prioritized Backlog

### P0 (Next)
- Semantic Migration Sprint 2: reservation writes, room block create/release, folio open/charge, outbox + shadow mode

### P1
- Semantic Migration Sprint 3: stay aggregate writes (room assign/move, check-in/out, extend) with state machine + rollback playbook
- Semantic Migration Sprint 4: finance risk paths (payment, refund, invoice) with idempotency + reconciliation
- Redis-based Caching (replace in-memory SimpleCache)
- Continue server.py modularization (target: <35K lines - POS, maintenance, sales/CRM, dashboard routes)

### P2
- Remaining i18n gaps (Quick Actions, minor headers)
- server.py further reduction (target: <30K lines)
- Complete i18n for POS, Staff, Mobile Dashboard pages

## Key Endpoints
| Endpoint | Method | Router | Description |
|----------|--------|--------|-------------|
| /api/auth/login | POST | auth.py | Login |
| /api/auth/me | GET | auth.py | Current user |
| /api/pms/rooms | GET/POST | pms.py | Room management |
| /api/pms/bookings | GET/POST | pms.py | Booking management |
| /api/pms/dashboard | GET | pms.py | PMS stats |
| /api/folio/* | GET/POST | finance.py | Folio management |
| /api/accounting/* | GET/POST | finance.py | Accounting |
| /api/cashiering/* | GET/POST | finance.py | Cashiering |
| /api/reports/* | GET/POST | reports.py | Reports |
| /api/night-audit/* | GET/POST | reports.py | Night Audit |
| /api/housekeeping/* | GET/POST | housekeeping.py | Housekeeping |
| /api/department/*/dashboard | GET | departments.py | Dept dashboards |

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
| Housekeeping | housekeeping@hotel.com | staff123 |
| Finance | finance@hotel.com | staff123 |
| Sales | sales@hotel.com | staff123 |
