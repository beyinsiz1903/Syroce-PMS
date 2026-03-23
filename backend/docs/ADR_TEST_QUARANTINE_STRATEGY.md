# ADR-002: Test Quarantine & Triage Strategy

## Status: ACCEPTED
## Date: 2026-03-23

## Context

The Syroce PMS test suite has accumulated ~1,400+ tests across multiple development phases.
Current state as of Sprint 3:
- **~1,721 passing** tests
- **~403 failing** tests 
- **~590 skipped** tests
- **~856 errors** (import/setup failures, not assertion failures)

Many "failures" are actually import errors from tests written against old interfaces
or tests that depend on external services/stale seed data.

## Decision

### Tier System

We adopt a 3-tier test classification:

| Tier | Name | CI Gate? | Location | Description |
|------|------|----------|----------|-------------|
| **T0** | Battle Tests | YES (hard gate) | `tests/battle/` | Booking invariants, regression guards. MUST pass for every release. |
| **T1** | Curated Suite | YES (hard gate) | Listed in `ci-cd.yml` | Hand-picked integration + unit tests known to be stable. |
| **T2** | Quarantine | NO (informational) | `tests/_quarantine/` | Failing/flaky tests moved here. Reviewed monthly. |

### T0: Battle Tests (Release Blockers)
```
tests/battle/test_booking_integrity.py       # 10 tests - INV-1 through INV-6
tests/battle/test_sprint2_hold_ooo.py        # 10 tests - Hold TTL + OOO
tests/battle/test_regression_guards.py       # 9 tests  - Past date, navigation, dates
tests/battle/test_cancellation_edges.py      # 3 tests  - Cancel edge cases
tests/battle/test_folio_ledger.py            # 8 tests  - Folio integrity
tests/battle/test_learning_loop.py           # 6 tests  - Learning loop
```

### T1: Curated CI Suite
Current files in `ci-cd.yml` backend-test step. These are stable, 
well-maintained tests that cover core functionality.

### T2: Quarantine Rules

A test enters quarantine when:
1. It fails due to **stale fixtures** (DB data from old seed scripts)
2. It fails due to **removed/renamed API endpoints**
3. It fails due to **import errors** from refactored modules
4. It is **flaky** (intermittent failures unrelated to code changes)

A test exits quarantine when:
1. The root cause is fixed (updated fixture, new import path)
2. The test is rewritten against current API
3. The test is deleted (functionality no longer exists)

### Quarantine Process

```
1. Identify failing test → check error type
2. If import/setup error → move to _quarantine/, add comment with date + reason
3. If assertion error → investigate: is the test wrong or is the code broken?
4. If flaky → move to _quarantine/ with [FLAKY] tag
5. Monthly review: attempt to fix/delete quarantined tests
```

### Error Categories (from current ~1,259 non-passing tests)

| Category | Count (est.) | Action |
|----------|-------------|--------|
| Import errors (module moved/renamed) | ~500 | Quarantine, fix imports in batch |
| Stale DB fixtures | ~200 | Quarantine, update seed data |
| Removed/changed API endpoints | ~150 | Quarantine, rewrite or delete |
| Assertion failures (real bugs?) | ~50 | Investigate, file issues |
| Flaky (timing, concurrency) | ~50 | Quarantine with [FLAKY] tag |
| Rate limit exhaustion | ~50+ | Fixed via TESTING=1 env var |
| External service dependency | ~50+ | Quarantine, mock in tests |

## Consequences

- CI pipeline remains fast and reliable (only T0+T1 run)
- No "green washing" — failing tests are visible in quarantine, not silenced
- Monthly triage prevents quarantine from becoming a dumping ground
- New features MUST add T0 battle tests before merge
