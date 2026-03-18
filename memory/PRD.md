# Syroce PMS — Product Requirements Document

## Original Problem Statement
Enterprise-grade Property Management System (PMS) for hotel operations. The current strategic direction shifted from "building a good product" to "proving a production-ready system." Focus is on live reliability via `observe -> stress -> verify -> rollout -> prove`.

## Core System
- Multi-tenant PMS with Room Management, Reservations, Front Desk, Folio/Billing, Housekeeping, Night Audit
- Channel Manager integration (Exely SOAP API, HotelRunner REST API)
- Rate Manager with dynamic availability
- Runtime Cockpit with WebSocket state snapshot streaming
- Production Readiness scoring, 1-Click Safe Actions, Narrow Rollout Framework
- Unassigned reservation workflow with drag-and-drop room assignment

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

### Bug Fixes & Features — 2026-03-17 Session 2 (COMPLETED & TESTED)
1. **Exely Cancellation Sync (FIXED):**
   - `auto_import.py`: Added `process_pending_cancellations()` that propagates Exely cancellations to PMS bookings
   - `exely_pull_worker.py`: Now always runs auto_import (including cancellation processing) after every pull cycle
   - `reservation_import_service.py`: `_cancel_pms_booking` now creates OTA cancellation notification
2. **Cancelled Bookings Calendar Filter (FIXED):**
   - `ReservationCalendar.js`: `getBookingForRoomOnDate` now excludes cancelled/checked_out/no_show bookings
   - Also fixed: `isRoomOccupiedOnDay`, `detectConflicts`, `handleFindRoom` all filter cancelled bookings
3. **Unassigned Reservation Row (NEW FEATURE):**
   - OTA-imported bookings arrive with `room_id=null`, `room_type` set (no auto room assignment)
   - Calendar shows "ATANMAMIS" (Unassigned) row under each room type header for unassigned bookings
   - Amber-styled booking bars with dashed border, "Surukle -> Oda" instruction
   - Room type header shows "X atanmamis" badge count
4. **Drag-and-Drop Room Assignment (NEW FEATURE):**
   - User drags booking from unassigned row to a specific room
   - `handleAssignRoom` calls `PUT /api/pms/bookings/{id}` with new room_id
   - Toast notification confirms assignment
5. **OTA Sync Button (NEW FEATURE):**
   - "OTA Sync" button in calendar header triggers manual reservation pull from all active connectors
   - Shows loading state during sync, reports results (imported/cancelled counts)
6. **Calendar Sidebar Cancel Button (NEW FEATURE):**
   - Cancel button in ReservationSidebar for non-cancelled bookings
   - Calls `POST /api/pms-core/cancel` with confirmation dialog
   - Auto-refreshes calendar data after cancellation
7. **Room Type Enrichment (FIX):**
   - `reservation_read_service.py` now enriches `room_type` from rooms collection
   - Both cached and non-cached booking query paths include room_type

### Bug Fixes — 2026-03-18 (COMPLETED & TESTED — 100% pass rate)
1. **OTA Sync Button URL Fix (BUG FIX):**
   - `ReservationCalendar.js`: `handleSyncReservations` now calls the correct Exely endpoint `POST /channel-manager/exely/sync/reservations/pull` and v2 connector flow `/channel-manager/v2/connectors`
   - Previously called non-existent `/channel-manager/connectors` which silently failed
2. **Individual Cancellation Detection (BUG FIX):**
   - `exely_router.py`: Added `_check_individual_cancellations()` that checks each imported reservation individually via Exely SOAP to detect cancellations the batch "Undelivered" pull may miss
   - `soap_builder.py`: Fixed `build_read_rq` to include `SelectionCriteria` element for individual reservation lookups (Exely requires it)
3. **Unassigned Bookings Overlap Fix (BUG FIX):**
   - `ReservationCalendar.js`: Added `computeUnassignedLanes()` lane allocation algorithm that assigns vertical lanes to overlapping bookings
   - Unassigned row height dynamically expands based on number of overlapping booking lanes
   - Each booking positioned at its computed lane offset to prevent visual overlap

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
│   ├── domains/channel_manager/providers/exely/ (auto_import, pull_worker, normalizer)
│   ├── modules/pms_core/ (reservation state machine, front desk, folio)
│   ├── modules/reservations/ (repository, read/create/update services)
│   ├── routers/ (pms, pms_hardening, enterprise, housekeeping)
│   └── tests/
└── frontend/src/
    ├── pages/ (PMSModule, RateManager, ReservationCalendar, RuntimeCockpit)
    └── components/ (ReservationSidebar, pms/BookingDetailDialog, etc.)
```

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
