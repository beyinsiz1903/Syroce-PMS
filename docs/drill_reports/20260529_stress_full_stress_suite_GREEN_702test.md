# Full Stress Suite — GREEN — 702 test (2026-05-29) — Run #161

## Status: ✅ OFFICIAL BASELINE — supersedes Run #159

This drill report records an **official GitHub Actions full-stress-suite
artifact** whose metric values clear every promotion gate AND whose
provenance (run URL + run number + commit SHA) is fully documented.

As of 2026-05-29, **Run #161 (commit `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`)
is the official stress baseline**, superseding Run #159
(`e23a4ec603cc32984b741d77d67d57a0abba698b`, now historical reference) and
Run #143 (`3b3891d`, older historical reference). Pointer moved in
`replit.md`, `docs/STRESS_TEST_ROADMAP.md`, and
`docs/TEST_COVERAGE_SCORECARD_100.md`.

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
| duration | 3441.6s (~57m 22s) | — | — |
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

**All promotion requirements met.** Pointer moved to Run #161.

## Verdict discipline

- The verdict is **GO WITH WATCH**, NOT GO. This report does **not**
  claim GO. The "WATCH" qualifier stands: 65 P2 + 48 REVIEW + 1 P3 +
  61 SKIP remain open and are **not downgraded**.
- This is a **web/backend full stress suite baseline** promotion, NOT
  /100 coverage completion. Mobile (F10) remains ZERO/unverified;
  backend deep routers, reports/AI deep, and frontend mutation flows
  remain uncovered. This artifact does not change the `/100`
  surface-coverage score beyond the covered web/backend-stress surface.
- REVIEW (48) and P2 (65) are held at their reported severity. No
  reclassification to clear the verdict.

## Comparison vs Run #159 (previous official baseline)

| Metric | Run #159 (2026-05-28) | This artifact — Run #161 (2026-05-29) |
|---|---|---|
| commit SHA | `e23a4ec603cc32984b741d77d67d57a0abba698b` | `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67` |
| totalTests | 702 | 702 |
| failedTests | 0 | 0 |
| PASS / FAIL / REVIEW / SKIP | 1314 / 0 / 48 / 61 | 1314 / 0 / 48 / 61 |
| P0 / P1 | 0 / 0 | 0 / 0 |
| P2 | 65 | 65 |
| P3 | 1 | 1 |
| external_calls | [] | [] |
| pilot_drift | 0 | 0 |
| cleanup idempotent | yes (7756→0) | yes (7756→0) |
| verdict | GO WITH WATCH | GO WITH WATCH |
| duration | 3623.6s (~60m 24s) | 3441.6s (~57m 22s) |

Run #161 reproduces the Run #159 green metric profile on a newer commit
(`ba9dfc7`) with all critical gates equal or green. It is a valid
successor and becomes the official pointer.

## Provenance capture block (COMPLETED)

```
Workflow               : Full Stress Suite (one-shot)
GitHub Actions run URL : https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26641150604
GitHub Actions run num : #161
Run ID                 : 26641150604
Job ID                 : 78514272098
Commit SHA (run target): ba9dfc7aafc0a694b70841d3405f8445ecfc1b67
Branch                 : main
Run date (UTC)         : 2026-05-29
Artifact (drill report): stress-drill-report, ID 7293609890,
                         digest sha256:61b789a04ae724b46691d80026ecd279bf08f51a2ebc10affde8fc7bda615fb9
Artifact (pw report)   : playwright-stress-report, ID 7293609632,
                         digest sha256:f7b8efdc13f27c4238c7e4c0443b2c980d83b9fda30260f6214925a1c4090ada
```

## Promotion checklist (COMPLETED)

- [x] Run URL recorded above
- [x] Run number recorded above (#161)
- [x] Commit SHA recorded above (`ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`)
- [x] `docs/STRESS_TEST_ROADMAP.md` — latest verified baseline updated to Run #161 / 2026-05-29 / 702 test / `ba9dfc7`; Run #159 moved to historical reference; Run #143 kept as older historical reference
- [x] `docs/TEST_COVERAGE_SCORECARD_100.md` — official pointer updated to Run #161 (full-suite artifact present; /100 NOT achieved; mobile/F10 open)
- [x] `replit.md` — F8 Stress Test Series baseline pointer updated to Run #161 / 2026-05-29 / 702 test / `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67` / GO WITH WATCH; Run #159 marked historical reference

All boxes checked. **Run #161 (`ba9dfc7`) is the official baseline.**

## Standing rules (reaffirmed)

- No fake green. Metric values without run URL + commit SHA are not a
  movable baseline.
- No artifact, no baseline. (Provenance IS part of the artifact.)
- Do not claim GO when verdict is GO WITH WATCH.
- Do not claim /100 coverage; this is web/backend full-stress baseline
  promotion only.
- Do not claim mobile/F10 verified — it remains separate and open.
- Do not downgrade P2 / REVIEW / SKIP to clean the verdict.

## Cross-references

- `docs/drill_reports/20260528_stress_full_stress_suite_GREEN_702test.md` — Run #159 baseline (historical reference)
- `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` — Run #143 baseline (older historical reference)
- `docs/TEST_COVERAGE_SCORECARD_100.md` — /100 scorecard (central reference)
- `docs/STRESS_TEST_ROADMAP.md` — roadmap / latest verified baseline
- `replit.md` — baseline pointer source of truth
