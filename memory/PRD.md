# Syroce PMS - Product Requirements Document

## Problem Statement
Turkish hotel Property Management System (PMS) for managing reservations, rooms, guests, folios, and financial operations. Full-stack application with React frontend and FastAPI backend.

## Core Features
- Reservation Calendar with drag/drop, booking bars, room assignment
- Reservation Detail Modal (10 tabs) - opened via double-click on booking bar
- Folio Management: Payments, Cari transfers, Agency payments, Reconciliation
- Room Management: Room change, availability tracking
- Guest Management: CRUD, VIP status, communication logs
- Group Booking Management
- Deposit Tracking
- Channel Manager (Exely) integration
- Night Audit Dashboard
- Housekeeping Status Management
- Wake-up Call Management
- Lost & Found Module
- Admin Tenant Management (CRUD, modules, teams, stats)

## Architecture
- Frontend: React + TailwindCSS + Shadcn/UI
- Backend: FastAPI + MongoDB
- Authentication: JWT-based
- Routing: /api prefix for all backend routes

### Calendar Architecture (Refactored)
```
/app/frontend/src/pages/
  ReservationCalendar.js       (~800 lines - main orchestrator)
  calendar/
    CalendarHeader.js          (header, navigation, buttons)
    CalendarGrid.js            (room grid, booking bars, drag/drop, past date styling)
    CalendarOccupancy.js       (occupancy chart SVG)
    CalendarDialogs.js         (NewBooking, Details, MoveReason, FindRoom)
    calendarHelpers.js         (pure utility functions incl. isPastDate)
    index.js                   (barrel exports)
```

### Admin Tenants Architecture (Refactored - Session 27)
```
/app/frontend/src/pages/
  AdminTenants.js              (main orchestrator, ~300 lines)
  admin/
    tenantConstants.js         (PLANS, MODULE_GROUPS, ROLE_LABELS)
    CreateTenantModal.js       (new hotel creation form)
    EditTenantModal.js         (edit hotel info)
    TeamManagementModal.js     (per-hotel team CRUD, role management)
    AllUsersView.js            (all users list with filters)
    TenantStatsPanel.js        (per-tenant stats: rooms, users, guests, bookings)
```

## Key API Endpoints
- POST /api/auth/login
- GET/POST /api/pms/bookings
- PUT /api/pms/bookings/{id}
- GET /api/pms/guests/search?q=...
- GET /api/pms/reservations/{id}/full-detail
- POST /api/pms/reservations/{id}/record-payment
- POST /api/pms/reservations/{id}/cancel
- GET /api/pms/reservations/{id}/voucher
- POST /api/pms/reservations/{id}/generate-invoice
- GET /api/pms/available-rooms-by-type
- POST /api/pms/cari-accounts/create
- POST /api/pms/quick-booking
- GET /api/night-audit/business-date
- POST /api/night-audit/run
- GET/PUT /api/night-audit/schedule
- GET /api/night-audit/financial-summary
- GET /api/pms/group-folio-summary
- POST /api/pms/group-folio/bulk-payment
- GET /api/admin/tenants
- POST /api/admin/tenants
- PATCH /api/admin/tenants/{id}/info
- PATCH /api/admin/tenants/{id}/modules
- PATCH /api/admin/tenants/{id}/tier
- PATCH /api/admin/tenants/{id}/subscription
- GET /api/admin/tenants/{id}/team
- POST /api/admin/tenants/{id}/team
- DELETE /api/admin/tenants/{id}/team/{user_id}
- PATCH /api/admin/tenants/{id}/team/{user_id}/role
- GET /api/admin/tenants/{id}/stats
- GET /api/admin/users

## Credentials
- Demo Admin: demo@hotel.com / demo123

## Completed (Session 36 - Mar 2026)
- [x] Bug Fix: Guest search field missing in Calendar "Hızlı Rezervasyon" dialog
  - Root cause: NewBookingDialog in CalendarDialogs.js used plain <select> dropdown instead of search input
  - Fix: Added debounced guest search with autocomplete in CalendarDialogs.js (same UX as RoomsTab.js)
  - Features: Search input with icon, debounced API call (300ms), dropdown results, selected guest blue card, clear button, "new guest" hint
  - Tested: Backend 3/3 (100%) + Frontend 100% (iteration_110.json)

## Completed (Session 35 - Feb 2026)
- [x] Bug Fix: ResizeObserver error overlay in "Create New Booking" dialog
  - Root cause: CRA error overlay capturing benign ResizeObserver loop errors triggered by Radix UI Select
  - Fix: Added early error suppression script in `public/index.html` <head> before any bundle scripts
  - Verified: Both "Hizli Rezervasyon" and "Create New Booking" dialogs open without error overlay

## Completed (Session 34 - Feb 2026)
- [x] P4: Quick reservation - existing guest search
  - Backend: `GET /api/pms/guests/search?q=...` endpoint (name, email, phone, id_number search)
  - Backend: `QuickBookingCreate` now accepts optional `guest_id` to use existing guest
  - Frontend: Guest search field with debounced autocomplete in quick reservation dialog
  - Frontend: Selected guest display with blue info box and clear button
  - Tested: Backend 10/10 (100%) + Frontend 100% (iteration_109.json)

## Completed (Session 33 - Feb 2026)
- [x] P0: User verified refactoring of RateManager and ReservationDetailModal - confirmed working
- [x] P3: Added unit tests for refactored components (32 tests, 3 test suites, 100% pass)
- [x] P3: soap_builder.py cleanup reviewed - no commented-out code found, file is clean
- [x] Installed @testing-library/react, @testing-library/jest-dom, @testing-library/dom, @testing-library/user-event
- [x] Configured Jest moduleNameMapper for @/ alias in package.json

## Completed (Session 32 - Feb 2026)
- [x] Fixed CI test failure in `test_p6_readiness_rollout.py::TestAPIEndpoints::test_all_p6_endpoints`
- [x] P2 Refactoring: ReservationDetailModal.js (1385 -> 183 lines + 6 sub-files)
- [x] P2 Refactoring: RateManager.jsx (1034 -> 296 lines + 4 sub-files)

## Backlog (Future Tasks)
- [x] P1: Enhance "Hızlı Rezervasyon" dialog on calendar with guest search (consistency with quick reservation) - DONE Session 36
- [ ] P1: Mapping UI Improvement (PMS room/rate <-> Provider mapping interface)
- [ ] P1: Test booking creation via Exely booking link + OTA_ReadRQ verification
- [ ] P1: Reservation lineage - duplicate/stale detection
- [ ] P2: Legacy collection cleanup
- [ ] P2: Deprecation cleanup (remove old files)
- [ ] P3: Service Wiring, Schema Completion, Frontend Role-Based Views
- [ ] P5: Rate Manager: "Stop Sale" functionality
- [ ] P5: Folio Management: Deposit/refund flows and invoice generation
