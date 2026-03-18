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

## Architecture
- Frontend: React + TailwindCSS + Shadcn/UI
- Backend: FastAPI + MongoDB
- Authentication: JWT-based
- Routing: /api prefix for all backend routes

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
- [x] ReservationCalendar.js refactoring (CalendarDialogs, CalendarWidgets)

### Session 5 (Current - Mar 18, 2026)
- [x] Fixed balance calculation (now includes total_amount in folio balance)
- [x] Added "Giris Yap" (Check-in) button to modal sidebar (conditional on confirmed status)
- [x] Added "Cikis Yap" (Check-out) button to modal sidebar (conditional on checked_in status)
- [x] Added "Acenteye Aktar" button to Folyolar tab (transfer cari to agency)
- [x] Added "Mahsuplastir" button to Folyolar tab (cari reconciliation/offset)
- [x] Added "room_service/Oda Servisi" category to extra charges dropdown
- [x] New API: POST /api/pms/cari-accounts/{id}/reconcile
- [x] New API: POST /api/pms/cari-accounts/{id}/transfer-to-agency
- [x] All tested: 17/17 backend tests passed, all frontend features verified

### Session 6 (Mar 18, 2026 - P2 Features)
- [x] **Housekeeping Status Management** - Room clean/dirty/inspected/maintenance/out_of_order status within room grid, bulk update, filtering, search
- [x] **Wake-up Call Management** - Full CRUD with scheduling, status tracking (pending/completed/missed/cancelled), method selection (phone/system/both), recurring support
- [x] **Lost & Found Module** - Item registration with category (electronics/clothing/jewelry/docs/bags), guest matching via booking ID, status flow (found → stored → claimed → returned)
- [x] **Hotel Settings for Invoice** - New "Fatura Ayarlari" tab in Settings page with logo upload, hotel name, tax info, currency, invoice header/footer
- [x] **PDF Invoice from Folio** - "PDF Fatura" button in reservation's Folyolar tab, generates styled HTML invoice with hotel branding, print support
- [x] **Group Folio Merging** - Merge group member folios into a master folio with payment transfer, merge history log
- [x] **Auto-Dirty on Checkout** - Room housekeeping_status automatically set to "dirty" when guest checks out (individual + group checkout)
- [x] New API endpoints in /app/backend/routers/hotel_services.py (17 routes)
- [x] 4 new frontend pages: HousekeepingStatusPage, WakeUpCallsPage, LostFoundPage, GroupFolioPage
- [x] All tested: Backend 100%, Frontend 100% (iteration_89.json)

## Key API Endpoints
- POST /api/auth/login
- GET/POST /api/pms/bookings
- PUT /api/pms/bookings/{id} (with Idempotency-Key header)
- GET /api/pms/reservations/{id}/full-detail
- POST /api/pms/reservations/{id}/record-payment
- POST /api/pms/reservations/{id}/transfer-to-cari
- POST /api/pms/reservations/{id}/record-agency-payment
- POST /api/pms/reservations/{id}/add-extra-charge
- POST /api/pms/reservations/{id}/split-charge
- POST /api/pms/reservations/{id}/room-change
- POST /api/pms/cari-accounts/{id}/reconcile
- POST /api/pms/cari-accounts/{id}/transfer-to-agency
- GET /api/pms/available-rooms
- GET /api/pms/housekeeping/rooms
- PUT /api/pms/housekeeping/rooms/{id}/status
- GET/POST /api/pms/wake-up-calls
- PUT/DELETE /api/pms/wake-up-calls/{id}
- GET/POST /api/pms/lost-found
- PUT/DELETE /api/pms/lost-found/{id}
- POST /api/pms/lost-found/{id}/match-guest
- GET/PUT /api/pms/hotel-settings
- GET /api/pms/reservations/{id}/invoice-pdf
- POST /api/pms/group-folio/merge
- GET /api/pms/group-folio/{id}

## Credentials
- Demo Admin: demo@hotel.com / demo123

## Backlog (Future Tasks)
- [x] ~~P1: Housekeeping Integration~~ (DONE - Session 6)
- [x] ~~P2: Wake-up Call Management~~ (DONE - Session 6)
- [x] ~~P3: Lost & Found Module~~ (DONE - Session 6)
- [x] ~~P4: PDF Invoice/Receipt from Folio~~ (DONE - Session 6)
- [x] ~~P5: Group Folio Merging~~ (DONE - Session 6)
- [ ] P5: Advanced Auto-Heal, Deprecated Code Cleanup
- [ ] P5: Financial Module Hardening (Night Audit)
- [ ] P5: Tenant Management
- [ ] Ongoing: ReservationCalendar.js further refactoring
