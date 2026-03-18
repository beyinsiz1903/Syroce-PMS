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

## Credentials
- Demo Admin: demo@hotel.com / demo123

## Backlog (Future Tasks)
- [ ] P1: Housekeeping Integration
- [ ] P2: Wake-up Call Management
- [ ] P3: Lost & Found Module
- [ ] P4: PDF Invoice/Receipt from Folio
- [ ] P5: Group Folio Merging
- [ ] P5: Advanced Auto-Heal, Deprecated Code Cleanup
- [ ] P5: Financial Module Hardening (Night Audit)
- [ ] P5: Tenant Management
- [ ] Ongoing: ReservationCalendar.js further refactoring
