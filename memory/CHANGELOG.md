# Syroce PMS — Changelog

## 2026-03-22 — CHAOS-001: Chaos Testing & Resilience Validation Program
- Created comprehensive 10-part chaos testing master plan (`backend/docs/CHAOS_TESTING_MASTER_PLAN.md`, 1187 lines)
- Built resilience test harness at `backend/tests/resilience/` (7 test files, 2579 LOC)
- Implemented and validated 69 resilience tests — all passing:
  - `test_provider_failures.py` (15 tests): Taxonomy classification, timeout handling, duplicate prevention, backlog drain
  - `test_worker_failures.py` (9 tests): 429 retry, stuck recovery, atomic claim race, delay detection, dead-letter visibility
  - `test_retry_replay.py` (10 tests): Dry-run safety (ZERO mutation), resolved failure rejection, replay idempotency, key rotation, lifecycle
  - `test_crypto_resilience.py` (8 tests): AAD context binding, malformed envelope, tamper detection, key rotation, encryption properties
  - `test_tenant_isolation.py` (8 tests): Unauthorized access denial, cross-tenant blocking, audit trail, policy enforcement
  - `test_ops_visibility.py` (12 tests): Failure visibility, stuck outbox detection, alert threshold, cooldown, anomaly detection, runbook availability
  - `test_burst_soak.py` (7 tests): 50-reservation burst, ARI storm (100 events), anomaly flood (50 denied), aggregation accuracy under load
- Created chaos injection fixtures: mock providers, crypto helpers, DB helpers, factory fixtures
- Added pytest markers (chaos_l1-l4) and CI/CD cadence configuration
- Added `KeyRing._from_test()` classmethod for isolated crypto testing
- Zero regressions: all 38 existing control plane tests still pass

## 2026-03-22 (earlier) — OPS-001: Production-Grade Control Plane
- Created `/app/backend/controlplane/` module (9 files)
- 15 API endpoints under `/api/ops/*`
- Failure taxonomy, retry engine, alerting, runbooks, startup validator
- 38 unit tests + 29 API tests — all passing
