# Full Stress Suite — GREEN — 702 test (2026-05-29) — Run #162

## Status: ✅ OFFICIAL BASELINE — supersedes Run #161

This drill report records an **official GitHub Actions full-stress-suite
artifact** whose metric values clear every promotion gate AND whose
provenance (run URL + run number + run ID + job ID + commit SHA +
artifact IDs + artifact digests) is fully documented.

As of 2026-05-29, **Run #162 (commit `bde7662744c9b94a5c9294fa778202d813319dfc`)
is the official stress baseline**, superseding Run #161
(`ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`, now historical reference),
Run #159 (`e23a4ec603cc32984b741d77d67d57a0abba698b`, older historical
reference) and Run #143 (`3b3891d`, oldest historical reference). Pointer
moved in `digitalocean.md`, `docs/STRESS_TEST_ROADMAP.md`, and
`docs/TEST_COVERAGE_SCORECARD_100.md`.

This run validates the **Wave 1–5 P2/REVIEW cleanup candidate changes**
(test-only + docs + one C420 lint fix; no production behavior change).

## Artifact metrics (as received)

| Metric | Value | Gate | Pass? |
|---|---|---|---|
| totalTests | 702 | — | — |
| failedTests | 0 | = 0 | ✅ |
| PASS | 1316 | — | — |
| FAIL | 0 | = 0 | ✅ |
| REVIEW | 46 | not downgraded | ✅ (held as REVIEW) |
| SKIP | 61 | skip ≠ pass | ✅ (held as SKIP) |
| P0 | 0 | = 0 | ✅ |
| P1 | 0 | = 0 | ✅ |
| P2 | 60 | not downgraded | ✅ (held as P2) |
| P3 | 1 | informational | ✅ |
| duration | 3576.2s (~59m 36s) | — | — |
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
- provenance documented (run URL + run ID + job ID + commit SHA +
  artifact IDs + digests) ✅

**All promotion requirements met.** Pointer moved to Run #162.

## Verdict discipline

- The verdict is **GO WITH WATCH**, NOT GO. This report does **not**
  claim GO. The "WATCH" qualifier stands: 60 P2 + 46 REVIEW + 1 P3 +
  61 SKIP remain open and are **not downgraded**.
- This is a **web/backend full stress suite baseline** promotion, NOT
  /100 coverage completion. Mobile (F10) remains separate and unverified
  unless separately proven; backend deep routers, reports/AI deep, and
  frontend mutation flows remain uncovered. This artifact does not
  change the `/100` surface-coverage score beyond the covered
  web/backend-stress surface.
- REVIEW (46) and P2 (60) are held at their reported severity. No
  reclassification to clear the verdict.

## Comparison vs Run #161 (previous official baseline — now historical reference)

| Metric | Run #161 (2026-05-29) — historical | This artifact — Run #162 (2026-05-29) — official |
|---|---|---|
| commit SHA | `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67` | `bde7662744c9b94a5c9294fa778202d813319dfc` |
| run URL | https://github.com/beyinsiz1903/syroce-pms/actions/runs/26641150604 | https://github.com/beyinsiz1903/syroce-pms/actions/runs/26653464472 |
| run ID / job ID | 26641150604 / 78514272098 | 26653464472 / 78557501168 |
| totalTests | 702 | 702 |
| failedTests | 0 | 0 |
| PASS / FAIL / REVIEW / SKIP | 1314 / 0 / 48 / 61 | 1316 / 0 / 46 / 61 |
| P0 / P1 | 0 / 0 | 0 / 0 |
| P2 | 65 | 60 |
| P3 | 1 | 1 |
| external_calls | [] | [] |
| pilot_drift | 0 | 0 |
| cleanup idempotent | yes (7756→0) | yes (7756→0) |
| verdict | GO WITH WATCH | GO WITH WATCH |
| duration | 3441.6s (~57m 22s) | 3576.2s (~59m 36s) |

Run #162 reproduces the green metric profile on a newer commit
(`bde7662`) with all critical gates equal or green, and reflects the
Wave 1–5 cleanup effect: REVIEW 48→46, P2 65→60, PASS 1314→1316. It is a
valid successor and becomes the official pointer. Run #161 is moved to
historical reference.

## Provenance capture block (COMPLETED)

```
Workflow               : Full Stress Suite (one-shot)
GitHub Actions run URL : https://github.com/beyinsiz1903/syroce-pms/actions/runs/26653464472
GitHub Actions run num : #162
Run ID                 : 26653464472
Job ID                 : 78557501168
Commit SHA (run target): bde7662744c9b94a5c9294fa778202d813319dfc
Branch                 : main
Run date (UTC)         : 2026-05-29T17:57:53Z
Artifact (drill report): stress-drill-report, ID 7298692917,
                         digest sha256:ca8a84b03c07972ad70024284082f5f93d69f779ea441d21103dd24e6d266d28
Artifact (pw report)   : playwright-stress-report, ID 7298692578,
                         digest sha256:89f2e67d44099ba6ce603c1c5c4fd92bdee33966e7bd3b8c84b1e59c7939be07
```

## Promotion checklist (COMPLETED)

- [x] Run URL recorded above
- [x] Run number recorded above (#162)
- [x] Run ID + Job ID recorded above (26653464472 / 78557501168)
- [x] Commit SHA recorded above (`bde7662744c9b94a5c9294fa778202d813319dfc`)
- [x] Artifact IDs + digests recorded above (both artifacts)
- [x] `docs/STRESS_TEST_ROADMAP.md` — latest verified baseline updated to Run #162 / 2026-05-29 / 702 test / `bde7662`; Run #161 moved to historical reference; Run #159/#143 kept as older historical references
- [x] `docs/TEST_COVERAGE_SCORECARD_100.md` — official pointer updated to Run #162 (full-suite artifact present; /100 NOT achieved; mobile/F10 open)
- [x] `digitalocean.md` — F8 Stress Test Series baseline pointer updated to Run #162 / 2026-05-29 / 702 test / `bde7662744c9b94a5c9294fa778202d813319dfc` / GO WITH WATCH; Run #161 marked historical reference

All boxes checked. **Run #162 (`bde7662`) is the official baseline.**

## Standing rules (reaffirmed)

- No fake green. Metric values without run URL + run ID + commit SHA +
  artifact digests are not a movable baseline.
- No artifact, no baseline. (Provenance IS part of the artifact.)
- Do not claim GO when verdict is GO WITH WATCH.
- Do not claim /100 coverage; this is web/backend full-stress baseline
  promotion only.
- Do not claim mobile/F10 verified — it remains separate and open.
- Do not downgrade P2 / REVIEW / SKIP to clean the verdict.

## Cross-references

- Run #161 baseline (historical reference) — provenance + metrics preserved in the comparison block above
- `docs/drill_reports/20260528_stress_full_stress_suite_GREEN_702test.md` — Run #159 baseline (older historical reference)
- `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` — Run #143 baseline (oldest historical reference)
- `docs/TEST_COVERAGE_SCORECARD_100.md` — /100 scorecard (central reference)
- `docs/STRESS_TEST_ROADMAP.md` — roadmap / latest verified baseline
- `digitalocean.md` — baseline pointer source of truth
