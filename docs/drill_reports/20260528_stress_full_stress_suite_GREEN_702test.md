# Full Stress Suite — GREEN — 702 test (2026-05-28) — Run #159

## Status: ✅ OFFICIAL BASELINE — supersedes Run #143

This drill report records an **official GitHub Actions full-stress-suite
artifact** whose metric values clear every promotion gate AND whose
provenance (run URL + run number + commit SHA) is fully documented.

As of 2026-05-28, **Run #159 (commit `e23a4ec603cc32984b741d77d67d57a0abba698b`)
is the official stress baseline**, superseding Run #143 (`3b3891d`,
now historical reference). Pointer moved in `digitalocean.md`,
`docs/STRESS_TEST_ROADMAP.md`, and `docs/TEST_COVERAGE_SCORECARD_100.md`.

## Artifact metrics (as received)

| Metric | Value | Gate | Pass? |
|---|---|---|---|
| totalTests | 702 | — | — |
| failedTests | 0 | = 0 | ✅ |
| PASS | 1314 | — | — |
| FAIL | 0 | = 0 | ✅ |
| REVIEW | 48 | not downgraded | ✅ (held as REVIEW) |
| SKIP | 61 | skip ≠ pass | ✅ (held as SKIP) |
| P0 | 0 | = 0 | ✅ |
| P1 | 0 | = 0 | ✅ |
| P2 | 65 | not downgraded | ✅ (held as P2) |
| P3 | 1 | informational | ✅ |
| duration | 3623.6s (~60m 24s) | — | — |
| verdict | **GO WITH WATCH** | ≥ GO WITH WATCH | ✅ |
| external_calls | [] | = [] | ✅ |
| pilot_drift | 0 | = 0 | ✅ |
| cleanup#1 deleted_total | 7756 | — | — |
| cleanup#2 deleted_total | 0 (idempotent=true) | idempotent | ✅ |

## Gate evaluation

All numeric and safety gates are satisfied:

- `failedTests = 0` ✅
- `P0 = 0` ✅
- `P1 = 0` ✅
- `external_calls = []` ✅
- `pilot_drift = 0` ✅
- cleanup idempotent (`cleanup#2 deleted_total = 0`) ✅
- `verdict ≥ GO WITH WATCH` ✅ (verdict IS exactly GO WITH WATCH)
- provenance documented (run URL + run number + commit SHA) ✅

**All promotion requirements met.** Pointer moved to Run #159.

## Verdict discipline

- The verdict is **GO WITH WATCH**, NOT GO. This report does **not**
  claim GO. The "WATCH" qualifier stands: 65 P2 + 48 REVIEW + 1 P3 +
  61 SKIP remain open and are **not downgraded**.
- This is a **full stress suite baseline promotion**, NOT /100
  coverage completion. Mobile (F10) remains ZERO; backend deep routers,
  reports/AI deep, and frontend mutation flows remain uncovered. This
  artifact does not change the `/100` surface-coverage score beyond the
  covered web-stress surface.
- REVIEW (48) and P2 (65) are held at their reported severity. No
  reclassification to clear the verdict.

## Comparison vs Run #143 (current official baseline)

| Metric | Run #143 (2026-05-26) | This artifact (2026-05-28) |
|---|---|---|
| commit SHA | `3b3891d` | `e23a4ec603cc32984b741d77d67d57a0abba698b` |
| spec count | 84 | (suite expanded) |
| totalTests | 556 | 702 |
| failedTests | 0 | 0 |
| P0 / P1 | 0 / 0 | 0 / 0 |
| P2 | 60 | 65 |
| P3 | 1 | 1 |
| REVIEW | — | 48 |
| SKIP | — | 61 |
| external_calls | [] | [] |
| pilot_drift | 0 | 0 |
| cleanup idempotent | yes | yes |
| verdict | GO WITH WATCH | GO WITH WATCH |
| duration | ~47m | ~60m 24s |

This 2026-05-28 artifact is a strict superset of Run #143's coverage
(702 vs 556 tests, 84→ expanded specs) with all critical gates equal
or green. It is a valid successor candidate — pending provenance.

## Provenance capture block (COMPLETED)

```
Workflow               : Full Stress Suite (one-shot)
GitHub Actions run URL : https://github.com/beyinsiz1903/syroce-pms/actions/runs/26601324830
GitHub Actions run num : #159
Run ID                 : 26601324830
Job ID                 : 78385405937
Commit SHA (run target): e23a4ec603cc32984b741d77d67d57a0abba698b
Branch                 : main
Run date (UTC)         : 2026-05-28
Artifact (drill report): stress-drill-report, ID 7278147196,
                         digest sha256:c496b9f70fccebbf096e3136e0a91d92a9afd9aff63c3d46aac56fe1f09f6a26
Artifact (pw report)   : playwright-stress-report, ID 7278146888,
                         digest sha256:42e61c005505e729eecb9fc36951ceb26b4ee2433a6178c64e88eb06c3d37d5b
```

## Promotion checklist (COMPLETED)

- [x] Run URL recorded above
- [x] Run number recorded above (#159)
- [x] Commit SHA recorded above (`e23a4ec603cc32984b741d77d67d57a0abba698b`)
- [x] `docs/STRESS_TEST_ROADMAP.md` — latest verified baseline updated to Run #159 / 2026-05-28 / 702 test / `e23a4ec`; Run #143 moved to historical reference
- [x] `docs/TEST_COVERAGE_SCORECARD_100.md` — official score block updated (full-suite artifact present; official score → 84/100; /100 NOT achieved; mobile/F10 open)
- [x] `digitalocean.md` — F8 Stress Test Series baseline pointer updated to Run #159 / 2026-05-28 / 702 test / `e23a4ec603cc32984b741d77d67d57a0abba698b` / GO WITH WATCH; Run #143 marked historical reference

All boxes checked. **Run #159 (`e23a4ec`) is the official baseline.**

## Standing rules (reaffirmed)

- No fake green. Metric values without run URL + commit SHA are not a
  movable baseline.
- No artifact, no baseline. (Provenance IS part of the artifact.)
- Do not claim GO when verdict is GO WITH WATCH.
- Do not claim /100 coverage; this is full-stress baseline promotion only.
- Do not downgrade P2 / REVIEW / SKIP to clean the verdict.

## Cross-references

- `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` — Run #143 baseline (current official)
- `docs/TEST_COVERAGE_SCORECARD_100.md` — /100 scorecard (central reference)
- `docs/DAILY_CHANGE_REVIEW_20260528_POST_UPDATES.md` — post-#143 commit inventory
- `docs/STRESS_TEST_ROADMAP.md` — roadmap / latest verified baseline
- `digitalocean.md` — baseline pointer source of truth
