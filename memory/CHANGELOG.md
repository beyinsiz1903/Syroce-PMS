# Changelog

## [2026-03-30] P1 Ops Dashboard Frontend
- Created `/api/channel/hotelrunner-v2/ops-dashboard` aggregated backend endpoint
- Built `HRv2OpsDashboard.jsx` React page with 7 panels (Provider Health, Operational Actions, Sync Overview, Failure Visibility, Recent Events, Recent Drifts, Operations Breakdown)
- Added route `/hrv2-ops` in App.jsx
- Fixed tenant context mismatch (JWT tenant vs query param tenant) with set_tenant_context override
- Turkish language UI labels throughout
- All interactive elements with data-testid attributes
- Testing: 13/13 backend tests, 100% frontend verification (iteration 163)

## [2026-03-30] P0 Live Production Test
- Verified real HotelRunner API connectivity (auth, rooms, reservations, channels)
- Shadow mode confirmed stable, DLQ empty, no errors
- Production credentials seeded in credential vault

## [2026-03-30] HotelRunner v2 Connector
- Built production-grade connector with 17 REST endpoints
- Client, mapper, retry, metrics, reconciliation, feature flags
- 33/33 tests passed
