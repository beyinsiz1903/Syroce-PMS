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

### Calendar UX - Direct Room Booking (Session Latest)
- When clicking a room cell in the calendar grid, the booking dialog shows the selected room info directly without room type/room selection dropdowns
- When clicking "Rezervasyon ekle" button in the header, the full room selection is shown
- Drag-and-drop for room/date changes is already implemented
- **Past date reservation prevention (3-layer):**
  - Frontend: Calendar cell click blocks past dates with toast error
  - Frontend: Date input min attribute prevents past date selection
  - Backend: API validates check-in date >= today, returns 400 for past dates

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

### Session 11b (Mar 19, 2026)
- [x] **Toplu Odeme (Bulk Payment)** - Group-level bulk payment distribution
  - Backend: POST /api/pms/group-folio/bulk-payment with 3 distribution methods (proportional, equal, balance_only)
  - Frontend: "Toplu Odeme" button in group detail, dialog with amount, distribution preview, payment method
  - "Bakiye tutarini doldur" quick-fill button, real-time distribution preview per booking
- [x] All tested: Backend 100% (3/3) + Frontend 100% (iteration_96.json)

### Session 12 (Mar 19, 2026)
- [x] **11 Calendar & Reservation Improvements**
  1. Calendar "Rezervasyonlar" button active - navigates to /pms?tab=bookings
  2. "Rezervasyon ekle" dialog - room type dropdown + room selection working
  3. "Tarihe Git" - functional date picker popup with "Bugun" shortcut
  4. Calendar nav arrows - overlapping scroll (SCROLL_DAYS = daysToShow/3) instead of full page jump
  5. Genel Bakis (FindRoom) - check-out auto-sets from check-in date
  6. Calendar colors simplified: green (checked_in), red (checked_out/past), gray (future). Agency names/colors removed
  7. Room change dialog - shows room types with availability count, available rooms per type, upgrade pricing options (current/upgrade/custom)
  8. Voucher tab - generates professional HTML voucher, print/PDF support
  9. Cancel tab - reason selection, cancel types, no-show option with charge (per night/full stay/custom)
  10. Invoice tab - billing info fields, selectable charge items, professional HTML invoice, print/PDF
  11. Cari transfer - "Yeni Cari Olustur" button with full account creation form
- [x] **New Backend Endpoints**:
  - POST /api/pms/reservations/{id}/cancel
  - GET /api/pms/reservations/{id}/voucher
  - GET /api/pms/reservations/{id}/invoice-charges
  - POST /api/pms/reservations/{id}/generate-invoice
  - GET /api/pms/available-rooms-by-type
  - POST /api/pms/cari-accounts/create
- [x] All tested: Backend 15/15 + Frontend 100% (iteration_97.json)

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
- POST /api/pms/group-folio/bulk-payment
- POST /api/pms/reservations/{id}/cancel
- GET /api/pms/reservations/{id}/voucher
- GET /api/pms/reservations/{id}/invoice-charges
- POST /api/pms/reservations/{id}/generate-invoice
- GET /api/pms/available-rooms-by-type
- POST /api/pms/cari-accounts/create

## Credentials
- Demo Admin: demo@hotel.com / demo123

### Session 13 (Mar 19, 2026)
- [x] **Past Date Reservation Prevention (Bug Fix)**
  - Frontend: `handleCellClick` blocks past date clicks with toast error "Gecmis tarihe rezervasyon yapilamaz"
  - Frontend: `NewBookingDialog` check-in input `min` attribute set to today's date
  - Frontend: `handleCreateBooking` validates check-in date before form submission
  - Backend: `CreateReservationService.create()` validates check_in >= today, returns HTTP 400
  - Modified files: ReservationCalendar.js, CalendarDialogs.js, create_reservation_service.py
  - All tested: Backend curl tests passed (400 for past, 200 for today)

## Backlog (Future Tasks)
- [ ] P1: Tenant Management page improvements (detail view, data summary, access logs)
- [ ] P2: Refactor ReservationDetailModal.js (1400+ lines → smaller components)
- [ ] P5: Advanced Auto-Heal patterns (remaining)
