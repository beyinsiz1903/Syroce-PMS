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
