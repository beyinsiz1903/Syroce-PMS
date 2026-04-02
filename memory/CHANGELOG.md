# CHANGELOG

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
