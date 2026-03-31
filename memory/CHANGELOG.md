# CHANGELOG

## [2026-03-31] Phase 9 — E2E Reservation Test Suite
- Created comprehensive E2E test suite: `/app/backend/tests/test_e2e_reservation_flow.py`
- 34 test cases covering full reservation lifecycle
- Set up test infrastructure: mock credentials (test-tenant/hotelrunner/mock), room mappings (DLX, STD, SUI, FAM), rate plan mappings (BAR, PROMO, RACK, NONREF)
- Fixed lint issues in `dry_run.py` (unused import, import ordering) and `router.py` (import ordering)
- Fixed Redis installation for Celery Beat support
- Testing agent validation: 34/34 backend tests PASSED, 19/19 frontend panels verified (iteration_167.json)

## [2026-03-30] Phase 8 — Shadow Automation (Celery Beat)
- Created `shadow_automation.py` for automation logic (snapshot, summary, alerts, retention)
- Configured Celery Beat schedule in `celery_app.py` and tasks in `celery_tasks.py`
- Added new trend and automation API endpoints in `router.py`
- Added "Shadow Otomasyon" and "Trendler" panels to `HRv2OpsDashboard.jsx`
- Redis + Celery Worker + Beat via Supervisor
- Testing: 14/14 APIs passed, 5 UI panels verified (iteration_166.json)

## [2026-03-30] Phase 7 — Dry-Run Write Path
- Created `dry_run.py` with full dry-run engine (NO-OP external calls, failure simulation, chain test)
- 7 new API endpoints for dry-run operations
- Dashboard: Dry-Run Kontrol, Hata Dagilimi, Write Acma Kriterleri panels

## [2026-03-30] Phase 6 — Shadow Observation & Write Path Plan
- `observation.py` — Daily snapshot collection, alert thresholds
- `readiness.py` — Write Readiness Score (0-100)
- `transition.py` — 4-phase transition plan

## [2026-03-30] Phase 5 — Ops Dashboard Frontend
- `HRv2OpsDashboard.jsx` with 11+ panels

## [2026-03-30] Phase 4 — Live Production Test
- All endpoints tested against real HotelRunner API

## [2026-03-30] Phase 3 — HotelRunner v2 Connector
- Full production-grade connector with 10 modules
