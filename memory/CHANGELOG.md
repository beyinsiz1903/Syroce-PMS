# Changelog

## [2026-03-31] P1 Shadow Automation (Celery Beat)
- Created `shadow_automation.py` — Full automation engine for shadow observation period
- 6-hourly tasks: provider health snapshot, sync metrics, drift, DLQ/retry, readiness score recalculation, automatic dry-run chain test, alert generation
- Daily summary: 24h trend report (readiness/drift/latency/failure trends, score delta vs previous day, chain test summary, alert count)
- Alert rules: readiness_low (<70, critical), readiness_warn (70-85, warn), drift_high (>=5, critical), dlq_nonempty (>0, critical), auth_failure (>0, critical), dry_run_chain_fail (critical)
- Retention: raw snapshots 30 days, daily summaries 90 days, alerts 60 days (weekly cleanup via Celery Beat)
- Celery Beat schedules: hrv2-shadow-snapshot (6h), hrv2-daily-summary (00:00 UTC), hrv2-retention-cleanup (Sun 05:00 UTC)
- 6 new API endpoints: automation/status, automation/trigger, automation/trends, automation/alerts, automation/alerts/acknowledge, automation/daily-summaries
- Updated ops-dashboard to include automation.status and automation.trends
- Frontend: Shadow Otomasyon panel (status, schedule, active alerts, last snapshot/summary, retention info)
- Frontend: Manuel Snapshot Tetikle button with toast notification
- Frontend: 4 trend panels (Readiness, Drift, Latency, Failure) with color-coded bar charts and tooltips
- Supervisor config: Redis, Celery Worker (concurrency=2), Celery Beat
- Testing: 14/14 backend, 5/5 frontend panels verified (iteration 166)


## [2026-03-30] P1 Dry-Run Write Path
- Created `dry_run.py` — Full dry-run write engine with production-identical pipeline, NO-OP external calls
- Supported operations: ARI push, confirm delivery, create/modify/cancel chain
- Failure simulation: timeout, validation_error, rate_limit
- Payload consistency check, transaction verification (read-only with HR API fallback)
- Write Enable Criteria: 6 conditions (readiness>=90, drift<5, dry-run rate>=95%, DLQ=0, retry<5, chain success)
- Added 7 new endpoints: dry-run/ari-push, dry-run/confirm-delivery, dry-run/chain, dry-run/simulate-failure, dry-run/results, dry-run/stats, dry-run/write-criteria
- Updated ops-dashboard endpoint to include dry_run stats and write_criteria
- Frontend: Dry-Run Kontrol panel (ARI Push, Chain Test, 3 failure simulation buttons)
- Frontend: Dry-Run Hata Dagilimi panel (failure breakdown by category + per-operation)
- Frontend: Write Acma Kriterleri panel (6 criteria with met/not-met indicators)
- Added is_dry_run_mode() to feature_flags
- Testing: 14/14 backend, 100% frontend (iteration 165)

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
