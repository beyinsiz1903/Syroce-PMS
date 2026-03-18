# Syroce PMS - Product Requirements Document

## Original Problem Statement
Hotel PMS (Property Management System) for managing reservations, folios, guest operations, and front desk workflows with multi-channel integration (Exely, HotelRunner).

## Core Modules

### 1. Reservation Management
- Calendar-based reservation view with drag-and-drop
- Multi-channel booking integration (Exely, HotelRunner, Booking.com, Expedia)
- Booking creation with idempotency support

### 2. Reservation Detail Module (NEW - March 18, 2026)
Full-screen modal accessible by double-clicking a booking bar on the calendar.

**Tabs:**
- Genel Bilgiler (General Info): Dates, room, status, channel, guest contact
- Misafirler (Guests): Guest list with avatar, VIP status
- Folyolar (Folios): Payment recording, cari transfer, agency payment, transaction history
- Gunluk Fiyatlar (Daily Rates): Per-night pricing with edit capability
- Ek Ucretler (Extra Charges): Add/manage charges with categories, charge splitting to other rooms
- Notlar (Notes): Reservation notes with types (general/important/internal/guest_request)
- Gecmis (History): Full audit trail of all operations

**Left Sidebar Quick Actions:**
- Erken Giris (Early Check-in) with optional extra charge
- Gec Cikis (Late Check-out) with optional extra charge
- VIP toggle
- No-Show marking

**Folio Features:**
- Record payments (cash, card, bank transfer, online)
- Transfer to cari (account receivable) with account selection
- Record agency payments
- Split charges between rooms/folios
- Full activity logging for all operations

### 3. Cari (Account Receivable) System (NEW - March 18, 2026)
- Create/list cari accounts (company, agency, individual)
- Credit limits and payment terms
- Transaction tracking per account
- Transfer from reservation folio to cari

### 4. Folio Management
- Per-reservation folio with charges and payments
- Guest, agency, and company folio types
- Balance tracking

### 5. Front Desk Operations
- Room change with audit trail and folio transfer
- Early check-in / Late check-out management
- No-show handling with room release
- VIP guest management
- Deposit recording

### 6. Channel Manager Integration
- Exely integration with sync
- HotelRunner integration
- OTA rate plan management
- Independent rate plan selection per room type

## Architecture

### Backend
- FastAPI with MongoDB
- Key routers:
  - `/app/backend/routers/pms.py` - Core PMS operations
  - `/app/backend/routers/reservation_detail.py` - Reservation detail & front desk APIs (18 endpoints)
  - `/app/backend/bootstrap/router_registry.py` - Router registration

### Frontend
- React with Tailwind CSS + Shadcn UI
- Key components:
  - `/app/frontend/src/pages/ReservationCalendar.js` - Main calendar view (~2900 lines)
  - `/app/frontend/src/pages/ReservationDetailModal.js` - Full reservation detail modal (NEW)
  - `/app/frontend/src/pages/FolioDetailView.js` - Legacy folio view

### Database Collections
- `bookings` - Reservation records
- `guests` - Guest information
- `rooms` - Room inventory
- `folios` - Folio headers
- `folio_charges` - Folio line items
- `payments` - Payment records
- `extra_charges` - Extra charge records
- `reservation_notes` - Reservation notes
- `reservation_activity_log` - Audit trail
- `room_move_history` - Room change history
- `daily_rates` - Per-night pricing
- `cari_accounts` - Account receivable accounts
- `cari_transactions` - Cari account transactions
- `deposits` - Deposit records

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |

## Completed Work
- [x] Calendar UI redesign (March 2026)
- [x] Booking creation idempotency fix
- [x] Inline folio panel in calendar
- [x] **Reservation Detail Modal** (March 18, 2026) - Full implementation with all 7 tabs
- [x] **Cari Account System** (March 18, 2026)
- [x] **Front Desk Operations** (March 18, 2026) - Early check-in, late checkout, room change, no-show, VIP, deposit

## Pending/Future Tasks
- [ ] Oda degistirme UI (Room change UI within the modal)
- [ ] Grup rezervasyon yonetimi (Group booking management)
- [ ] Misafir iletisim gecmisi (Guest communication log - SMS/email)
- [ ] Depozito takip ekrani (Deposit tracking screen)
- [ ] Advanced Auto-Heal
- [ ] Deprecated code cleanup
- [ ] ProviderCapabilityMatrix finalization
- [ ] Financial Module Hardening
- [ ] Tenant Management with feature flags
- [ ] ReservationCalendar.js refactoring (break into sub-components)
