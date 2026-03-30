# Changelog

## [2026-03-30] P1 Shadow Observation & Write Path Plan
- Created `observation.py` — Daily snapshot collection, alert thresholds (8 metrics: drift, retry, DLQ, error rate, latency, auth, duplicate, stale), ingest consistency checks, daily report generation
- Created `readiness.py` — Write Readiness Score (0-100) with 5 weighted components: drift(25%), error_rate(25%), retry(15%), dlq(15%), latency(20%)
- Created `transition.py` — 4-phase transition plan (Shadow->Dry-Run->Limited Live->Full Live) with entry/exit/rollback criteria, state management, logging
- Added 8 new endpoints: readiness-score, observation/snapshot, observation/history, observation/report, observation/thresholds, transition/plan, transition/status, transition/history
- Updated ops-dashboard endpoint to include readiness score and transition phase data
- Updated feature_flags with dry_run_mode and limited_scope
- Frontend: Added Write Readiness Score circular gauge with component breakdown
- Frontend: Added Transition Phase Bar (4-phase progress indicator)
- Frontend: Added Observation Alerts panel with alert status badges
- Frontend: Added Observation History table with 7-day progress tracking
- Frontend: Added "Gunluk Snapshot Topla" button in operational actions
- Testing: 14/14 backend tests, 100% frontend verification (iteration 164)

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
