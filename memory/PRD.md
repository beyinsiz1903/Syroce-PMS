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

## Completed (Session 29 - Mar 20, 2026)
- [x] Fixed emergentintegrations install error in requirements.txt (added --extra-index-url)
- [x] Investigated React "duplicate key" warning - confirmed resolved, no warnings across all pages

## Backlog (Future Tasks)
- [ ] P2: Refactor ReservationDetailModal.js (1400+ lines -> smaller components)
- [ ] P3: Refactor RateManager.jsx (1000+ lines -> smaller components)
- [ ] P3: Clean up soap_builder.py (commented-out code from SOAP debugging)
- [ ] P4: Quick reservation - existing guest search
