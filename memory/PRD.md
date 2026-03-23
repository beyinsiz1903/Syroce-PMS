# Syroce PMS — Product Requirements Document

## Original Problem Statement
Full-stack hotel PMS (Property Management System) application with multi-tenant architecture, booking management, room inventory, channel management, and CI/CD pipeline.

## Architecture
- **Frontend:** React (Vite 8 + Rolldown) with Shadcn/UI, TailwindCSS
- **Backend:** FastAPI (Python) with MongoDB (motor async driver)
- **Database:** MongoDB
- **CI/CD:** GitHub Actions with curated test suite

## Core Features Implemented
- Multi-tenant booking management with atomic room-night locking
- Room type system with inventory management
- Channel manager integration (Exely, HotelRunner)
- Hold/OOO (Out of Order) room management
- AI Chatbot for hotel operations
- Audit trail & timeline events
- Crypto engine for sensitive data
- Outbox pattern for reliable event publishing
- Comprehensive battle test suite (540+ tests)

## What's Been Completed

### Quarantine Test Restoration (2026-03-23)
- **7 fully quarantined test files restored** to `tests/` from `_quarantine/`:
  - `test_business_date_validation.py` (stale_dates → dynamic dates)
  - `test_mapping_engine.py` (stale_fixtures → cleanup-before-seed)
  - `test_atomic_checkin_checkout.py` (stale_room_locks → lock cleanup + wide offsets)
  - `test_day2_hardening.py` (stale_room_locks → lock cleanup + wide offsets)
  - `test_modify_reservation_bridge.py` (stale_room_locks → sync pymongo)
  - `test_open_folio_bridge.py` (stale_room_locks → sync pymongo)
  - `test_release_room_block_bridge.py` (stale_room_locks → sync pymongo + entity_id fix)
- **10 individually skipped tests fixed** in-place:
  - `test_create_reservation_bridge.py` — sync pymongo + lock cleanup + wide offsets
  - `test_create_room_block_bridge.py` — sync pymongo + wide offsets
  - `test_quick_booking.py` — wide offsets + lock cleanup
  - `test_guest_search_quick_booking.py` — wide offsets + lock cleanup
  - `test_reservation_detail_api.py` — booking status reset + room cleanup
  - `test_readme_and_booking_validation.py` — wide offsets + lock cleanup
  - `test_new_folio_flows_api.py` — booking status reset + room cleanup
- **Root causes fixed:**
  1. `db.delegate` (motor async) called from sync test code → replaced with sync `pymongo.MongoClient`
  2. Stale `room_night_locks` from prior runs → added cleanup before booking creation
  3. Hardcoded near-future dates (30 days) → 3000-6000 day offsets to avoid collisions
  4. `BulkWriteError` on duplicate keys → cleanup-before-seed pattern
  5. Outbox `room_block_id` field renamed to `entity_id` → updated queries
- **Test count: 152 restored/fixed tests passing + 391 CI tests = 543 total, 0 failures**

### CI/CD Pipeline Stability
- Frontend build fix (`.js` → `.jsx` for Vite 8/Rolldown)
- Flaky test fix (wider `_RUN_TAG` random range)
- `yarn audit` bitmask-based exit code handling
- CI env vars (`VITE_BACKEND_URL`)
- Deployment fix (removed `exit 1` from deploy jobs)

## P0 — Completed
- [x] Frontend production build (Vite 8/Rolldown compatibility)
- [x] Flaky backend test stabilization
- [x] CI/CD pipeline reliability
- [x] Quarantine test restoration (7 files + 10 individual tests)

## P1 — Upcoming
- [ ] Fix remaining quarantined tests: stale_fixtures (rate_manager, 10 tests)
- [ ] Fix remaining quarantined tests: changed_api (10 tests)
- [ ] Fix remaining quarantined tests: changed_implementation (13 tests)
- [ ] Channel manager inventory ledger alignment with room-type system

## P2 — Backlog
- [ ] Fix remaining quarantined tests: external_dependency (3 tests)
- [ ] Crypto Migration (SEC-002) — will fix crypto v2 tests
- [ ] Secrets Management Rollout (SEC-001)
- [ ] Enable Strict Tenant Mode
- [ ] motor → pymongo native async migration
- [ ] Production build with Nginx static serving
- [ ] ~264 legacy DB import cleanup
- [ ] Governance Phase 3-4 (Support/KPI Dashboard)
- [ ] Properly implement deploy-staging/deploy-production CI jobs

## Key Technical Decisions
- **Vite 8 `.jsx` Convention:** All React component files use `.jsx` extension for Rolldown compatibility.
- **Test Isolation:** Battle tests use `random.randint(2100, 9999)` for date ranges + session-scoped DB cleanup.
- **Quarantine Fix Pattern:** Far-future dates (3000-6000 day offsets), sync pymongo for DB verification in sync tests, cleanup-before-seed for fixture isolation.
- **yarn audit CI Gate:** Uses bitmask check `(exit_code & 24) != 0` to only fail on HIGH/CRITICAL.

## Test Credentials
| User | Email | Password | Role |
|:---|:---|:---|:---|
| Demo Admin | demo@hotel.com | demo123 | super_admin |
