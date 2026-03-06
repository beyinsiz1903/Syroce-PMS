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

### Semantic Migration Test Hardening Pack (COMPLETED - Mar 2026)
- **Expanded contract snapshot tests:** added integration-level contract coverage for `/api/pms/bookings` (filtered, unfiltered, empty-list scenarios)
- **Expanded tenant/property isolation matrix:** added isolation harness coverage for `/api/pms/bookings`, `/api/pms/rooms/availability`, `/api/folio/{folio_id}`
- **Stabilized read contracts in tests:** availability and folio read response shape + nullability expectations are now explicitly tested
- **Files added/updated:** `backend/tests/test_semantic_read_contracts.py`, `backend/tests/harnesses/contract.py`, `backend/tests/harnesses/tenant_isolation.py`
- **Test result:** contract hardening suite **16/16 PASS**

### Shadow Metrics Start Pack (COMPLETED - Mar 2026)
- **Added instrumentation-only shadow compare layer:** availability and folio read paths now execute semantic response as primary path and compare against legacy logic in the background
- **Created shared shadow metrics utilities:** `backend/shared_kernel/shadow_metrics.py` provides canonical normalization, hashing, compare helpers, structured logging, and in-memory shadow metric counters
- **Activated shadow compare on live endpoints:** `/api/pms/rooms/availability` and `/api/folio/{folio_id}` now emit compare result, mismatch fields, hashes, tenant/property/correlation context, and duration without changing response contract
- **Added validation tests:** `backend/tests/test_shadow_metrics.py`
- **Validation:** shadow metrics tests **4/4 PASS**, combined contract + shadow suite **20/20 PASS**, backend + frontend smoke passed

### CreateReservation Bridge + Outbox Package (COMPLETED - Mar 2026)
- **Added semantic write service:** `backend/modules/reservations/services/create_reservation_service.py`
- **Bridged legacy endpoint:** `POST /api/pms/bookings` now calls the semantic create service while preserving legacy response contract
- **Added idempotency enforcement:** `Idempotency-Key` is now required for reservation creation; duplicate retry with same key returns the same reservation response
- **Added outbox + audit:** successful create now writes `reservation.created.v1` to `outbox_events` and creates `reservation_created` audit log entries
- **Added safety checks:** wrong property scope rejects with 403; wrong tenant using foreign room/guest rejects safely; missing key rejects with 400
- **Added regression tests:** `backend/tests/test_create_reservation_bridge.py`
- **Validation:** CreateReservation bridge suite **6/6 PASS**, backend validation **PASS**, frontend smoke **PASS**

### CreateRoomBlock Bridge + Outbox Package (COMPLETED - Mar 2026)
- **Added semantic inventory write service:** `backend/modules/inventory/services/create_room_block_service.py`
- **Bridged legacy endpoint:** active `POST /api/pms/room-blocks` path now calls the semantic inventory service while preserving response contract (`message`, `block`, `room_number`, `warnings`)
- **Added idempotency enforcement:** `Idempotency-Key` is now required for room block creation; duplicate retry returns the same block response
- **Added outbox + audit:** successful block create now writes `inventory.blocked.v1` to `outbox_events` and creates `room_block_created` audit log entries
- **Validated availability effect:** block create is reflected in availability read results without redesigning projection logic
- **Added regression tests:** `backend/tests/test_create_room_block_bridge.py`
- **Validation:** room block bridge suite **7/7 PASS**, backend validation **PASS**, frontend smoke **PASS**

### FolioOpen Bridge + Outbox Package (COMPLETED - Mar 2026)
- **Added semantic folio write service:** `backend/modules/folio/services/open_folio_service.py`
- **Bridged legacy endpoint:** active `POST /api/folio/create` path now calls the semantic folio service while preserving the existing folio response contract
- **Added idempotency enforcement:** `Idempotency-Key` is now required for folio open; duplicate retry with the same key returns the same folio, and duplicate open attempts for the same booking + folio type are rejected with `409`
- **Added outbox + audit:** successful folio open now writes `folio.opened.v1` to `outbox_events` and creates `folio_opened` audit log entries
- **Added finance validation:** booking reference is tenant-scoped, property scope mismatch rejects with `403`, and company/guest references are validated for supported folio types; folio records now persist resolved currency metadata for downstream read/event consumers
- **Added regression tests:** `backend/tests/test_open_folio_bridge.py`
- **Validation:** folio open bridge suite **7/7 PASS**, testing agent backend validation **PASS**, frontend smoke **PASS**

### Migration Observability Mini Panel (COMPLETED - Mar 2026)
- **Added backend observability service:** `backend/shared_kernel/migration_observability.py` aggregates migration-safe telemetry from `outbox_events`, `audit_logs`, and in-memory shadow metrics
- **Added reporting endpoint:** `GET /api/reports/migration-observability` returns outbox throughput, queue depth, event breakdown, retry/lag readiness, audit stream, and shadow mismatch summaries
- **Added dedicated frontend route:** `/app/migration-observability` with a separate operational control surface page and dashboard CTA entry point
- **Added UI coverage:** outbox chart/table, audit stream table, shadow summary cards, recent shadow events, refresh control, and `data-testid` coverage for critical elements
- **Added regression tests:** `backend/tests/test_migration_observability.py`
- **Validation:** observability suite **2/2 PASS**, combined backend validation **9/9 PASS**, backend API agent **PASS**, frontend testing agent **PASS**

### RoomBlockRelease Bridge + Outbox Package (COMPLETED - Mar 2026)
- **Added semantic inventory release service:** `backend/modules/inventory/services/release_room_block_service.py`
- **Bridged legacy release path:** active `POST /api/pms/room-blocks/{block_id}/cancel` path now calls the semantic release service from both duplicated legacy routers (`pms.py`, `housekeeping.py`) while preserving the legacy endpoint path
- **Added idempotency enforcement:** `Idempotency-Key` is now required for room block release; same-key retries return the same response and re-release with a new key returns deterministic final state without duplicating events
- **Added outbox + audit:** successful release now writes `inventory.released.v1` to `outbox_events` and creates `room_block_released` audit log entries with correlation metadata
- **Validated availability recovery:** blocked inventory becomes sellable again for the same property/date range after release; wrong tenant/property attempts do not mutate availability
- **Aligned frontend callers:** `frontend/src/pages/PMSModule.js` now sends `Idempotency-Key` for both room block create and room block release/cancel actions
- **Fixed auth UX regression:** hotel login button click is working correctly and protected `/pms` / `/app/pms` deep links now return to the intended PMS route after login
- **Added regression tests:** `backend/tests/test_release_room_block_bridge.py`
- **Validation:** create + release bridge suites **13/13 PASS** (+1 skipped availability fallback), backend deep testing **PASS**, frontend retest for auth/PMS redirect **PASS**

### Mini Migration Health Score (COMPLETED - Mar 2026)
- **Added backend health scoring layer:** `backend/shared_kernel/migration_observability.py` now computes `health_score` using approved thresholds for failed outbox events, stale pending queue, shadow mismatch rate, compare errors, and audit gap Red override
- **Added explicit contract:** `GET /api/reports/migration-observability` now returns `health_score { status, display_status, calculated_at, time_window, time_window_label, reasons, operational_guidance, signals }`
- **Added UI card on observability page:** `/app/migration-observability` now shows a dedicated Green/Yellow/Red health score card with last-24h window, calculated timestamp, max 3 short reasons, and signal breakdown
- **Added audit gap visibility:** response now exposes `audit.audit_gap_count` and uses audit-gap detection as a Red override in health scoring
- **Added regression tests:** expanded `backend/tests/test_migration_observability.py` with endpoint contract and threshold unit coverage
- **Validation:** health score suite **5/5 PASS**, backend deep validation **PASS**, frontend smoke/regression **PASS**

### Outbox Stale Pending Triage (COMPLETED - Mar 2026)
- **Added backend triage layer:** `backend/shared_kernel/migration_observability.py` now returns `outbox.stale_triage` with stale pending event-type breakdown, oldest/newest pending age, tenant/property/source/origin distribution, delivery lifecycle signals, and root-cause assessment
- **Observed live state:** current tenant has **120 stale pending** migration events, all within the same property and same-day backlog window; dominant types are `inventory.blocked.v1`, `reservation.created.v1`, `inventory.released.v1`, `folio.opened.v1`
- **Interpretation now explicit:** dashboard flags the backlog as **semantic-source**, with **0 processed** and **0 retry metadata** signals, pointing to likely **worker/consumer or state-transition lifecycle not active yet**
- **Frontend triage surface:** `/app/migration-observability` now includes a dedicated stale triage panel visible on initial load, so Yellow status is explained without switching tabs
- **Future data quality:** new semantic outbox writes now stamp payload `source` for reservation create, room block create, and folio open events to improve source attribution going forward
- **Validation:** migration observability tests **4 PASS / 2 skipped**, live API verification **PASS**, frontend selector smoke **PASS**

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
│   │   ├── inventory/         # Availability read abstraction + room block create/release write migrations
│   │   └── folio/             # Folio balance/detail reads + folio-open write migration
│   ├── shared_kernel/         # Tenant/event/audit/idempotency primitives (NEW)
│   │   └── migration_observability.py # Outbox/audit/shadow telemetry aggregation for migration control panel
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
- Outbox stale pending backlog için karar ver: consumer/worker bağlanacak mı, yoksa explicit park/cleanup policy mi tanımlanacak?
- Health score Yellow durumunu “açıklanmış ve kontrollü” seviyeye getirmeden `ModifyReservation` başlatılmayacak

### P1
- Semantic Migration Sprint 2: stale pending kararı sonrası `ModifyReservation`, sonra `CancelReservation` ve kontrollü `charge post`
- Migration observability paneline `processed_at`, retry metadata ve dead-letter lifecycle geldiğinde gerçek lag/retry grafikleri bağlanacak
- Health score kartına ileride trend/history ve cutover recommendation history eklenebilir
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
