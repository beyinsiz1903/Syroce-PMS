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
    CalendarGrid.js            (room grid, booking bars, drag/drop)
    CalendarOccupancy.js       (occupancy chart SVG)
    CalendarDialogs.js         (NewBooking, Details, MoveReason, FindRoom)
    calendarHelpers.js         (pure utility functions)
    index.js                   (barrel exports)
```

## What's Been Implemented

### Session 1-3 (Previous)
- [x] Full calendar view with booking bars
- [x] Room CRUD and management
- [x] Guest management
- [x] Booking CRUD with Idempotency-Key
- [x] Basic folio/charges/payments
- [x] Exely channel manager integration
- [x] Rate plan management
- [x] Dashboard

### Session 4 (Previous)
- [x] Reservation Detail Modal (10 tabs)
- [x] Room Change UI tab
- [x] Group Reservation Management page
- [x] Guest Communication History tab
- [x] Deposit Tracking page and tab
- [x] ReservationCalendar.js initial refactoring

### Session 5
- [x] Fixed balance calculation (now includes total_amount in folio balance)
- [x] Added Check-in/Check-out buttons to modal sidebar
- [x] Added "Acenteye Aktar" and "Mahsuplastir" buttons to Folyolar tab
- [x] Added "room_service/Oda Servisi" category to extra charges
- [x] New APIs: reconcile, transfer-to-agency
- [x] All tested: 17/17 backend tests passed

### Session 6 (P2 Features)
- [x] Housekeeping Status Management
- [x] Wake-up Call Management
- [x] Lost & Found Module
- [x] Hotel Settings for Invoice
- [x] PDF Invoice from Folio
- [x] Group Folio Merging
- [x] Auto-Dirty on Checkout

### Session 7 (Mar 18, 2026)
- [x] **Night Audit Dashboard** - New `/night-audit` page
- [x] **ReservationCalendar.js Refactoring** - Reduced from 2936 to ~800 lines
- [x] **Code Cleanup** - Removed .backup files
- [x] All tested: Frontend 100% (iteration_90.json)

### Session 8 (Mar 18, 2026)
- [x] **Night Audit Automatic Scheduling** - Full EOD automation with background scheduler
- [x] All tested: Backend 13/13 + Frontend 100% (iteration_91.json)

### Session 9 (Mar 18, 2026)
- [x] **Financial Module Hardening** - Comprehensive financial reporting and integrity system
- [x] All tested: Backend 31/31 + Frontend 100% (iteration_92.json)

### Session 10 (Mar 19, 2026)
- [x] **Top Navigation Simplification** - Major UX overhaul of the top menu bar
- [x] All tested: Frontend 100% (iteration_93.json, iteration_94.json)

### Session 11 (Mar 19, 2026)
- [x] **GroupFolioPage.js Full Implementation** - Enhanced from basic to fully functional
  - Summary stats cards (total groups, bookings, balance, merge operations)
  - Search/filter for groups
  - Expandable booking rows with folio line item details
  - Payment recording dialog (amount, method, reference)
  - Merge dialog with accessibility fix
  - Group total balance display
  - Merge history log
  - Backend: 3 new endpoints (group-folio-summary, group-folio/{id}/booking/{bid}, group-folio/payment)
- [x] **Deprecated Code Cleanup**
  - Deleted 5 unused frontend pages: GMDashboardOptimized, MarketplaceInventory, PMSModuleOptimized, PerformanceMonitorDashboard, TestLogin
  - Removed unused lazy imports from App.js: EnhancedGMDashboard, RevenueManagementMobile
  - Deleted deprecated backend files: server_pms_complete.py (788 lines), legacy_routes.py, scripts/ directory
  - Updated pyproject.toml and server.py docstring
- [x] **Dialog Accessibility Fix** - Auto-injected sr-only DialogDescription in Shadcn Dialog component to fix console warnings across all 29+ dialogs
- [x] All tested: Backend 7/7 + Frontend 100% (iteration_95.json)

## Key API Endpoints
- POST /api/auth/login
- GET/POST /api/pms/bookings
- PUT /api/pms/bookings/{id}
- GET /api/pms/reservations/{id}/full-detail
- POST /api/pms/reservations/{id}/record-payment
- POST /api/pms/reservations/{id}/transfer-to-cari
- POST /api/pms/reservations/{id}/record-agency-payment
- POST /api/pms/reservations/{id}/add-extra-charge
- POST /api/pms/reservations/{id}/split-charge
- POST /api/pms/reservations/{id}/room-change
- POST /api/pms/cari-accounts/{id}/reconcile
- POST /api/pms/cari-accounts/{id}/transfer-to-agency
- GET /api/night-audit/business-date
- POST /api/night-audit/run
- GET /api/night-audit/history
- GET /api/night-audit/exceptions/{audit_id}
- GET /api/night-audit/schedule
- PUT /api/night-audit/schedule
- GET /api/night-audit/schedule/status
- GET /api/night-audit/financial-summary
- GET /api/night-audit/payment-reconciliation
- GET /api/night-audit/financial-report
- GET /api/night-audit/integrity-check
- GET /api/pms/group-folio-summary
- GET /api/pms/group-folio/{group_id}
- GET /api/pms/group-folio/{group_id}/booking/{booking_id}
- POST /api/pms/group-folio/payment
- POST /api/pms/group-folio/merge

## Credentials
- Demo Admin: demo@hotel.com / demo123

## Backlog (Future Tasks)
- [ ] P1: Tenant Management page improvements (detail view, data summary, access logs)
- [ ] P5: Advanced Auto-Heal patterns (remaining)
