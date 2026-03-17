# Syroce PMS — Product Requirements Document

## Original Problem Statement
Enterprise-grade Property Management System (PMS) for hotel operations. The current strategic direction shifted from "building a good product" to "proving a production-ready system." Focus is on live reliability via `observe → stress → verify → rollout → prove`.

## Core System
- Multi-tenant PMS with Room Management, Reservations, Front Desk, Folio/Billing, Housekeeping, Night Audit
- Channel Manager integration (Exely SOAP API, HotelRunner REST API)
- Rate Manager with dynamic availability
- Runtime Cockpit with WebSocket state snapshot streaming
- Production Readiness scoring, 1-Click Safe Actions, Narrow Rollout Framework

## What's Been Implemented

### Phase 6: Production Readiness (COMPLETED)
- "Why NOT READY?" Scored Breakdown with prioritized blockers
- "1-Click Safe Actions" with idempotent, guarded operations
- "Narrow Rollout Framework" with automated gates
- WebSocket Cockpit with state snapshot streaming
- 88 passing tests

### Bug Fixes — 2026-03-17 (COMPLETED & TESTED)
1. **Reservation Cancellation Bug (FIXED):**
   - Frontend `BookingDetailDialog.js`: Cancel button now makes actual `POST /api/pms-core/cancel` API call
   - Backend `reservation_state_machine.py`: Creates notification on cancellation, restores availability in rate_calendar
   - Added `onBookingUpdated` callback to refresh bookings list after cancellation
2. **Inventory/Availability Bug (FIXED):**
   - Backend `rate_manager_router.py`: Grid now dynamically calculates availability = base - active bookings
   - Backend `routers/pms.py`: Allotment contracts endpoint dynamically calculates `used_rooms`
   - Frontend `RateManager.jsx`: Grid shows sold count with color coding for low availability

## Prioritized Backlog

### P0 — Execute Narrow Rollout
- Phase 1: Internal tenant, test property, HotelRunner only
- Phase 2: Add Exely provider
- Phase 3: Real small hotel, low traffic
- Phase 4: 7-day proof of reliability

### P1 — Advanced Auto-Heal
- Confidence scores, provider-specific rules

### P2 — Deprecated Code Cleanup
- Remove old provider files (hotelrunner.py, client.py, exely_client_legacy.py)

### P3 — Core Lockdown Blocks B & C
- ProviderCapabilityMatrix, Reconciliation Truth Table

### P4 — Financial Module Hardening
- Folio and Night Audit modules

### P4 — Tenant Management
- Per-tenant rollout gates, feature flags

## Known Issues
- WebSocket LIVE indicator doesn't work in preview environment (environmental, not code bug)
- Bookings cache can serve stale data for default query (minor, cache refreshes periodically)

## Architecture
```
/app
├── backend/
│   ├── domains/pms/ (core PMS, channel manager, revenue)
│   ├── modules/pms_core/ (reservation state machine, front desk, folio)
│   ├── routers/ (pms, pms_hardening, enterprise, housekeeping)
│   └── tests/
└── frontend/src/
    ├── pages/ (PMSModule, RateManager, ReservationCalendar, RuntimeCockpit)
    └── components/pms/ (BookingDetailDialog, BookingsTab, etc.)
```

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
