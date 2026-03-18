# Syroce PMS - Product Requirements Document

## Original Problem Statement
Hotel PMS (Property Management System) for managing reservations, folios, guest operations, and front desk workflows with multi-channel integration (Exely, HotelRunner).

## Core Modules

### 1. Reservation Calendar
- Calendar-based view with drag-and-drop
- Multi-channel booking integration
- Booking creation with idempotency

### 2. Reservation Detail Modal (March 18, 2026)
Full-screen modal with 10 tabs accessible via double-click on booking bar.

**Tabs:**
- Genel Bilgiler: Dates, room, status, channel, guest contact, edit capability
- Misafirler: Guest list with VIP badges
- Folyolar: Payment recording (cash/card/bank/online), cari transfer, agency payment
- Gunluk Fiyatlar: Per-night pricing with inline edit
- Ek Ucretler: Add charges with categories, split charges to other rooms
- Oda Degistir: Room change with available rooms dropdown, reason, audit trail
- Depozito: Record/refund deposits, summary cards
- Iletisim: SMS/email/phone/WhatsApp communication log
- Notlar: Notes with types (general/important/internal/guest_request)
- Gecmis: Full audit trail timeline

**Sidebar Quick Actions:** Erken Giris, Gec Cikis, VIP toggle, No-Show

### 3. Group Booking Management (March 18, 2026)
- Dedicated page at /group-bookings-manage
- Create groups with booking selection
- Toplu Giris (bulk check-in) / Toplu Cikis (bulk check-out)
- Group detail dialog with bookings table

### 4. Deposit Tracking (March 18, 2026)
- Dedicated page at /deposit-tracking with summary cards
- Record deposits, refund deposits
- Status tracking (active/partially refunded/refunded)

### 5. Communication Log (March 18, 2026)
- Per-reservation communication history
- Channels: email, SMS, phone, WhatsApp
- Directions: inbound/outbound
- Integrated in the reservation detail modal

### 6. Cari (Account Receivable) System
- Company/agency/individual accounts
- Transfer from reservation folio to cari
- Transaction tracking

### 7. Channel Manager Integration
- Exely, HotelRunner integrations
- OTA rate plan management

## Architecture

### Backend (FastAPI + MongoDB)
- `/app/backend/routers/pms.py` - Core PMS operations
- `/app/backend/routers/reservation_detail.py` - 30 endpoints for detail/folio/group/comm/deposit/room-change

### Frontend (React + Tailwind + Shadcn)
- `/app/frontend/src/pages/ReservationCalendar.js` - Main calendar
- `/app/frontend/src/pages/ReservationDetailModal.js` - 10-tab modal
- `/app/frontend/src/pages/GroupBookings.js` - Group management
- `/app/frontend/src/pages/DepositTracking.js` - Deposit tracking
- `/app/frontend/src/components/calendar/CalendarWidgets.js` - Extracted occupancy chart/stats
- `/app/frontend/src/components/calendar/CalendarDialogs.js` - Extracted dialogs

### Database Collections
bookings, guests, rooms, folios, folio_charges, payments, extra_charges, reservation_notes, reservation_activity_log, room_move_history, daily_rates, cari_accounts, cari_transactions, deposits, deposit_refunds, communication_logs, group_bookings, booking_guests, folio_operations

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |

## Completed Work
- [x] Calendar UI redesign
- [x] Booking creation idempotency fix
- [x] Reservation Detail Modal (10 tabs)
- [x] Cari Account System
- [x] Front Desk Operations (early check-in, late checkout, room change, no-show, VIP, deposit)
- [x] **Oda Degistir UI** (March 18, 2026) - Room change tab within modal
- [x] **Grup Rezervasyon Yonetimi** (March 18, 2026) - Dedicated page with bulk ops
- [x] **Misafir Iletisim Gecmisi** (March 18, 2026) - Communication log tab
- [x] **Depozito Takip Ekrani** (March 18, 2026) - Page + modal tab
- [x] **ReservationCalendar.js Refactoring** (March 18, 2026) - CalendarWidgets, CalendarDialogs extracted

## Pending/Future Tasks
- [ ] Advanced Auto-Heal
- [ ] Deprecated code cleanup
- [ ] ProviderCapabilityMatrix finalization
- [ ] Financial Module Hardening (Night Audit)
- [ ] Tenant Management with feature flags
- [ ] Housekeeping status integration
- [ ] Wake-up call management
- [ ] Lost & found tracking
