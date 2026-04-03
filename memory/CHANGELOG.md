# CHANGELOG

## 2026-04-03 - REFACTORING: hotelrunner_webhook.py Module Split

### Motivation
`hotelrunner_webhook.py` had grown to 1162 lines containing both webhook ingestion AND sync/polling logic, making it hard to maintain and navigate.

### Changes
Split into 3 focused modules:
- **`hotelrunner_shared.py`** (229 lines) — Shared utilities: `explode_multi_room_reservation`, `_persist_and_process`, `_timeline_append`, `_store_raw_payload`, `_resolve_property_id`
- **`hotelrunner_webhook.py`** (198 lines) — Webhook ingestion: `/webhooks/*`, `/logs/*`, `/sync/reservations/replay`
- **`hotelrunner_sync.py`** (780 lines) — Sync/polling: `ReservationPullScheduler`, `_sync_reservation_update`, Phase A/B, `/sync/*` endpoints

### Import Updates
- `bootstrap/router_registry.py`: Both `router` (webhook) and `sync_router` (sync) registered
- `startup.py`: `pull_scheduler` now imported from `hotelrunner_sync`
- `routers/hotelrunner_compat.py`: `_persist_and_process` now imported from `hotelrunner_shared`

### Verified
- 21/21 backend tests passed (iteration_182.json)
- All endpoints functional (webhooks, sync status, manual pull, logs)
- Scheduler auto-starts correctly from `startup.py`

---

## 2026-04-03 - BUG FIX: HotelRunner Global Cancellation Not Syncing

### Issue
When a user cancelled an entire reservation (all rooms) or cancelled additional rooms on HotelRunner, the cancellation was NOT being synced to the PMS. New reservations and name changes synced fine, but cancellations were silently dropped.

### Root Cause (Two-Part)
1. **Per-room effective state logic was too conservative**: Phase B's effective state calculation only checked room-level `state` field. For global cancellations, HR marks the top-level as cancelled (`next_states=['cancel']`) but does NOT update individual room states. Since room states remained "confirmed", the code kept them as confirmed.
2. **Poisoned timestamp problem**: The previous (buggy) sync cycle correctly updated `provider_updated_at` (from other changes like name/room type) but failed to apply the cancellation. This meant subsequent sync cycles saw `timestamp_changed=False` and skipped the reservation entirely.

### Fix — Three-Tier Per-Room State Logic
New algorithm in Phase B catch-up (`hotelrunner_webhook.py`):
1. Detect **new room-level cancellations** (rooms HR explicitly marks as cancelled that our DB still has as confirmed)
2. For each sub-room:
   - `_room_cancelled=True` → always "canceled"
   - Exploded room + top-level cancelled + **new partial cancel detected** → "confirmed" (respect room-level markers)
   - Exploded room + top-level cancelled + **no new room cancels** + **timestamp changed** → "canceled" (global cancel)
   - Exploded room + top-level cancelled + **no new room cancels** + **timestamp same** → keep stored status (avoid re-cancelling old partial cancels)

### Data Fix
Cleared `provider_updated_at` for non-cancelled rooms in 4 affected reservations (R881632298, R635472908, R676063586, R756101174) to force re-processing with corrected code. 17 rooms total were correctly updated to "cancelled" status.

### Verification
- R881632298: All 7 rooms → cancelled ✓
- R635472908: All 5 rooms → cancelled ✓
- R676063586: Both rooms → cancelled ✓
- R756101174: All 6 rooms → cancelled ✓
- R014235376: Rooms 0-1 cancelled, rooms 2-5 confirmed (partial cancel PRESERVED) ✓
- 17 cancellation notifications generated correctly
- Next Phase B cycle: `updated 0` (stable, no re-processing)

---


## 2026-04-03 - BUG FIX: HotelRunner Multi-Room Reservation Cancellation & Calendar Display

### Issues Fixed
1. **Multi-room partial cancellation spreading to ALL rooms**: When one room in a multi-room HR reservation was cancelled, Phase B was applying `effective_state=canceled` (from top-level `next_states=['cancel']`) to ALL sub-reservations, causing all 7 rooms to be incorrectly marked as cancelled.
2. **OTA bookings not appearing on reservation calendar**: Calendar's `getUnassignedBookingsForType` was matching by `room_type` only. OTA imports have HR display names (`Corner Süit`, `Deluxe Oda`) in `room_type`, while the calendar uses PMS names (`Suite`, `Deluxe`). The `room_type_id` field had the correct PMS mapping but wasn't being used.
3. **Modification notifications not being created**: Name changes, date changes, and cancellation updates from Phase B sync weren't generating in-app notifications.

### Root Causes
- `explode_multi_room_reservation()` didn't propagate per-room state (state, next_states, cancel_reason) from the room object
- Phase B used top-level `effective_state` for ALL sub-reservations instead of calculating per-room state
- `getUnassignedBookingsForType()` only compared `booking.room_type` with `roomType`, ignoring `room_type_id`
- `_sync_reservation_update` didn't create notifications for changes

### Changes
- **`hotelrunner_webhook.py` — `explode_multi_room_reservation()`**: Added per-room cancellation detection via `_room_cancelled` flag (checks room `state`, `status`, `cancel_reason`, `next_states`)
- **`hotelrunner_webhook.py` — Phase B pull loop**: Per-sub-reservation `sub_effective_state` calculation instead of blanket top-level state
- **`hotelrunner_webhook.py` — `_sync_reservation_update()`**: Added notification creation for status changes, guest name changes, and date changes
- **`normalizer.py` — `normalize_hotelrunner()`**: Added `_room_cancelled` flag check before status mapping
- **`import_bridge_service.py` — `create_import_record()`**: Added `provider_updated_at` field for accurate timestamp comparison in Phase B
- **`calendarHelpers.jsx` — `getUnassignedBookingsForType()`**: Added `room_type_id` matching alongside `room_type`
- **DB fix**: Restored 6 wrongly-cancelled R881632298 bookings to "confirmed" status (R881632298-1 remains correctly cancelled)
- **Lint fixes**: Removed 3 unused variable assignments and 1 unused import in `hotelrunner_webhook.py`

### Testing
- All 6 pytest tests passed (backend)
- Frontend calendar verified: 19 "murat sutay" booking elements visible, 4 "Atanmamis" rows present
- Test report: `/app/test_reports/iteration_181.json`



## 2026-04-03 - BUG FIX: HotelRunner Reservation Import Failure (Empty Email Unique Index)
### Root Cause
- `guests` collection had a global unique index on `email` field (`email_1`)
- When multiple guests had empty emails (HotelRunner often sends no guest email), the second insert failed with `E11000 duplicate key error`
- This caused `imported_reservations` to be marked as `failed` while `bookings` were never created

### Fixed
- **Dropped** problematic global `email_1` unique index on `guests` collection
- **Created** partial unique index `idx_guests_tenant_email_unique` — only enforces uniqueness for non-empty emails, scoped to `tenant_id`
- **Updated** `/app/backend/infra/database_optimizer.py` to prevent re-creation of the bad index
- **Updated** `/app/backend/startup.py` to drop legacy `email_1` index on startup
- **Retried** failed imports for R676063586 and R676063586-1 — both successfully created as bookings

### Impact
- All future HotelRunner reservations with empty guest emails will import correctly
- Existing failed imports can be retried via import retry worker



## 2026-04-02 - P2 Field Encryption Complete (users + bookings + guests)
### Added
- **Hash-based email lookups**: Auth login, register, forgot-password all use `build_user_email_query()` for dual-read (hash + plaintext) queries
- **`/api/ops/field-encryption/migrate-all`**: New endpoint to encrypt all configured collections at once
- **Auto-encryption on insert**: `auto_seed.py`, `atomic_booking.py`, `import_bridge_service.py`, `auth.py`, `admin/router.py` now encrypt PII fields before DB writes
- **`encrypted_lookup.py`**: New helper module with `build_user_email_query`, `encrypt_user_doc`, `decrypt_user_doc`, `encrypt_booking_doc`, `decrypt_booking_doc`

### Changed
- **`field_encryption.py` — `migrate_collection()`**: Now always sets `_enc_version=1` on processed documents, even when PII fields are empty
- **`core/security.py` — `get_current_user()`**: Now decrypts user document after DB read
- **`domains/admin/router.py`**: Admin user list and team list now decrypt user docs; create user encrypts before insert

### Encryption Status
- `guests`: 1/1 (100%), `users`: 158/158 (100%), `bookings`: 13/13 (100%)

### Verified
- Testing agent iteration_180: 100% pass rate (9/9 tests)


## 2026-04-02 - Calendar Vibrant Color Update
### Changed
- **Booking bar colors completely revamped**: Gray (#9ca3af) replaced with vibrant status-based colors:
  - **Blue (#2563eb)** → Confirmed future reservations
  - **Orange (#f97316)** → Today's arrivals
  - **Green (#16a34a)** → Checked-in (in-house) guests
  - **Teal (#0891b2)** → Guaranteed reservations
  - **Light red (#f87171)** → Past (not checked out)
  - **Slate (#94a3b8)** → Checked out/departed
- **Room type header background**: Amber/yellow → Blue-tinted (bg-blue-50)
- **Unassigned row styling**: Amber → Blue-tinted with blue pulse dot
- **Legend updated**: Now shows 4 color labels (Iceride, Bugun Gelis, Onaylanmis, Gecmis/Check-out)
- **Past date cells**: Lighter background (gray-100 instead of gray-200)
- **Occupancy chart gradient**: Updated to #3b82f6 blue

### Verified
- Testing agent iteration_179: 100% pass rate

## 2026-04-02 - Calendar Occupancy Fix & Compact UI
### Fixed
- **Critical Bug: Occupancy counter excluded unassigned reservations** — Room type header rows (e.g., Deluxe 0/8) now count both assigned and unassigned bookings. Previously, unassigned bookings (room_id=null) were excluded because the filter required a matching room object.
- **Root Cause**: `CalendarGrid.jsx` occupancy filter only looked at bookings with a valid `room_id` that matched a room in the room list. Unassigned bookings (room_id=null) were filtered out.

### Changed
- **Compact calendar grid**: Cell width 96px → 72px, booking bar height 46px → 30px, room row height 52px → 38px, room label width 128px → 112px
- **Bold reservation names**: Guest names on booking bars use `font-extrabold` (font-weight: 800)
- **Three-state occupancy dots**: Green (empty), orange (partially occupied), red (full) — was binary green/red
- **Smaller UI elements**: Date header text, A/D/S status badges, and group/AI indicators all reduced in size

### Verified
- Testing agent iteration_178: 100% pass rate (10/10 tests)
- Deluxe correctly shows 3/8 on dates with 3 unassigned bookings (was 0/8)
- Suite correctly shows 1/4 on dates with 1 unassigned booking (was 0/4)
- Drag & drop still functional (13 draggable elements confirmed)

## 2026-04-02 - HotelRunner Sync Improvements
### Added
- **30-second HR polling**: Pull scheduler interval decreased from 5 min to 30 sec
- **Unassigned room imports**: OTA bookings arrive as unassigned (room_id=None) for manual blocking
- **Import notifications**: notification_events_service.emit() on successful import
- **Catch-up pull**: Fetches all recent reservations (not just undelivered) to prevent missed bookings


# CHANGELOG

## 2026-03-31 - HotelRunner Oda Esleme (Room Mapping) UI
### Added
- **Eslemeler Tab**: Full room mapping UI - HotelRunner odalarini PMS oda tiplerine esleme
- **Backend Endpoints**: `GET /pms-room-types`, `GET /cached-rooms`, `POST /room-mappings/bulk`
- **Upsert Logic**: Existing mapping auto-updates on re-save (no duplicates)
- **Bulk Save**: "Tum Eslemeleri Kaydet" button for saving all mappings at once
- **New PMS Type**: "Yeni PMS Oda Tipi Ekle" input to create custom PMS room types
- **Delete Mapping**: Trash icon to remove individual mappings
- **Visual Feedback**: Green "Eslendi" badge for mapped rooms, amber warning for unmapped
- **Summary Bar**: Shows "X HR oda, Y esleme yapildi" with warning for missing mappings
- 9/9 pytest tests passing (iteration_168.json)

### Verified
- Corner Suit -> Suite, Standart Oda -> Standard, Deluxe Oda -> Deluxe mappings saved
- Bulk save, individual save, delete all working
- PMS room types dropdown populated from DB (Standard, Deluxe, Suite, Superior, Family, Junior Suite)

## 2026-03-31 - HotelRunner Connection Bug Fix
### Fixed
- **Critical Bug**: `HRConnectionSetup.environment` default was `"mock"` instead of `"production"`. All connection attempts from the UI were routed to the local mock server (localhost:9999) instead of the real HotelRunner API (app.hotelrunner.com). Changed default to `"production"`.
- **TypeError**: `test_result["duration_ms"]` and `test_result["channels"]` used dict subscript on a `ProviderResult` object. Fixed to use attribute access (`test_result.duration_ms`, `test_result.data.get("channels", [])`).
- Added debug logging to `/connect` endpoint showing target environment, URL, and masked credentials.

### Verified
- Real HotelRunner API connection successful with user's credentials (132 channels returned)
- UI shows "Bagli" (Connected) status with Syroce Hotel property name

## 2026-03-31 - E2E Pytest Test Suite (Previous Session)
### Added
- 34-case E2E test suite (`test_e2e_reservation_flow.py`) for reservation pipeline
- Tests cover: new/modify/cancel ingest, idempotency, duplicate rejection, dry-run, trace visibility
- Strict safety assertions: `shadow_mode=true`, `write_enabled=false`
- All tests passing (iteration_167.json)
