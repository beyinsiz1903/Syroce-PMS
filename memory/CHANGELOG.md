# CHANGELOG

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
