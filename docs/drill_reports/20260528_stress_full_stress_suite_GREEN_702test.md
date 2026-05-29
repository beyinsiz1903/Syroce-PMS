# Full Stress Suite — GREEN — 702 test (2026-05-28)

## Status: BASELINE PROMOTION CANDIDATE — pointer move BLOCKED on provenance

This drill report records an **official GitHub Actions full-stress-suite
artifact** whose metric values clear every promotion gate. However, the
baseline pointer is **NOT moved yet** because three provenance fields
are not yet documented:

- GitHub Actions **run URL** — **MISSING**
- GitHub Actions **run number** — **MISSING**
- **commit SHA** the run executed against — **MISSING**

Per standing doctrine (`docs/TEST_COVERAGE_SCORECARD_100.md`,
`docs/DAILY_CHANGE_REVIEW_20260528_POST_UPDATES.md`): **Run #143 can be
superseded only by this 2026-05-28 artifact AFTER the run URL + commit
SHA are documented.** Metric values alone do not move the pointer; the
provenance binds the artifact to a specific, auditable run and code
state. Until then, this is a candidate.

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

**Outstanding requirement for promotion**: run URL + run number +
commit SHA must be captured and recorded in this report. Without them,
the artifact cannot be bound to an auditable run and the pointer stays
at Run #143.

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
| commit SHA | `3b3891d` | **PENDING** |
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

## Provenance capture block (FILL TO PROMOTE)

```
GitHub Actions run URL : __________________________  (REQUIRED)
GitHub Actions run num : __________________________  (REQUIRED)
Commit SHA (run target): __________________________  (REQUIRED)
Workflow file          : .github/workflows/stress.yml (confirm)
Triggered by           : __________________________
Run date (UTC)         : 2026-05-28
```

## Promotion checklist (execute ONLY after provenance block is filled)

- [ ] Run URL recorded above
- [ ] Run number recorded above
- [ ] Commit SHA recorded above
- [ ] `docs/STRESS_TEST_ROADMAP.md` — latest verified baseline updated to 2026-05-28 / 702 test / <SHA>
- [ ] `docs/TEST_COVERAGE_SCORECARD_100.md` — official score block updated (full-suite artifact = present; note this is full-stress baseline, NOT /100)
- [ ] `replit.md` — F8 Stress Test Series baseline pointer updated to 2026-05-28 / 702 test / <SHA>, Run #143 marked historical reference

Until every box is checked, **Run #143 (`3b3891d`) remains the official
baseline** and the pointer does not move.

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
- `replit.md` — baseline pointer source of truth
