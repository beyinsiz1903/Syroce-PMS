# ADR-002: Test Quarantine & Triage Strategy

## Status: ACCEPTED
## Date: 2026-03-23

## Context

The Syroce PMS test suite has accumulated ~1,400+ tests across multiple development phases.
Current state as of 2026-09-09 (post-quarantine inventory audit):
- **6,600+ tests collected by the complete offline CI gate**
- **70+ tests restored** from quarantine (stale dates, stale room locks, stale fixtures)
- **0 active quarantine manifest entries**
- **0 duplicate test files retained under `tests/_quarantine/`**

The previous “~37 remaining” figure was stale documentation. The filesystem
still contained seven historical copies with 72 test functions, but each had a
maintained counterpart under `tests/`. Those copies were not additional test
coverage and were excluded by pytest discovery. They were removed in September
2026 so the repository no longer presents archived duplicates as active debt.

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

### Current Quarantine Inventory

The active inventory is empty. Any future entry must include a current pytest
node ID, owner, reason, entry date, and expiry date in
`tests/_quarantine/quarantine_manifest.py`. A copied test file without a
manifest entry is a policy failure, not an accepted quarantine.

### Restored from Quarantine (2026-03-23)

| Category | Tests Restored | Fix Applied |
|----------|---------------|-------------|
| stale_dates | 6 | Dynamic `datetime.now() + timedelta(...)` |
| stale_room_locks (file-level) | 48 | Lock cleanup + wide date offsets + sync pymongo |
| stale_room_locks (individual) | 14 | Same pattern, fixed in-place |
| stale_fixtures | 25 | cleanup-before-seed pattern |
| **Total** | **70+** | |

## Consequences

- CI pipeline remains fast and reliable (only T0+T1 run)
- No "green washing" — failing tests are visible in quarantine, not silenced
- Monthly triage prevents quarantine from becoming a dumping ground
- Historical copies live in git history, not in pytest-discoverable directories
- New features MUST add T0 battle tests before merge
