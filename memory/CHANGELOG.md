# CHANGELOG

## 2026-03-17 — Real Exely Test Environment Integration
- **SOAP Builder Rewrite**: Replaced WSSE UsernameToken with WSDL-defined PMSConnect Security header (`Username`/`Password` attributes in `https://www.hopenapi.com/Api/PMSConnect` namespace)
- **SOAPAction URIs**: All operations now use full WSDL-defined URIs (e.g., `https://www.hopenapi.com/Api/PMSConnect/HotelAvailRQ`)
- **ARI Push Fix**: BookingLimit moved from child element to attribute on AvailStatusMessage; Rate element now includes Start/End dates
- **Currency Default**: Changed from TRY to USD across all Exely operations
- **New Function**: `build_rate_amount_notif_rq` for OTA_HotelRateAmountNotifRQ (rate-only push)
- **Vault Integration**: `/connect` endpoint now stores credentials in encrypted vault; `_get_client` reads from vault first
- **Response Parser**: Updated to handle HopenAPI's `RoomDescription Name=` attribute format
- **Credential Security**: Connection status endpoint no longer exposes username/credentials_ref
- **Test Results**: 14/14 real API tests pass (testing agent), 77/77 unit tests pass, 14/14 integration tests pass

## 2026-03-14 — Production-Grade Exely SOAP Adapter
- Created multi-module adapter at `/app/backend/domains/channel_manager/providers/exely/`
- Implemented facade, SOAP client, error hierarchy, schemas
- Refactored all legacy call sites to use new ExelyProvider
- 77 unit + 14 integration tests (100% pass)
- CI pipeline fix: pytest.mark.skipif for tests requiring live server

## 2026-03-12 — Production-Grade HotelRunner REST Adapter
- Created `/app/backend/domains/channel_manager/providers/hotelrunner/`
- 80+ tests with production patterns
- Rate limiter, retry logic, observability

## Earlier
- Phase 1-5: PMS core, Front Desk, Night Audit, Revenue Engine, Channel Manager
- Slack integration, Dashboard, Calendar, PMS Operations
