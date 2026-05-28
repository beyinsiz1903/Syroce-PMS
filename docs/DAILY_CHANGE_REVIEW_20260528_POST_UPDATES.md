# Daily Change Review — 2026-05-28 Post-Updates

> **Authoritative baseline (UNCHANGED)**: Run #143, commit `3b3891d`, 84 spec / 556 test, verdict **GO WITH WATCH**.
> **Pointer movement**: BLOCKED until GitHub Actions full-suite artifact confirms `failedTests=0 / P0=0 / P1=0 / external_calls=[] / pilot_drift=0 / cleanup idempotent / verdict ≥ GO WITH WATCH`.
> **No fake green**. **No artifact, no baseline**.

This review enumerates every commit landed since baseline `3b3891d` (range
`3b3891d..afdd8a76`, 2026-05-27 → 2026-05-28). Each item is tagged with a
verification state. The cumulative work is a **strong candidate quality
uplift** but it is NOT a new baseline.

## Status legend

| Tag | Meaning |
|---|---|
| `shipped` | Code merged to main branch, deploy checkpoint exists |
| `targeted-verified` | Spec/unit test run against deployed backend with passing artifact attached to the source task |
| `replit-equivalent-verified` | Replit-environment full or partial suite run cited as candidate evidence (e.g. Task #57) — NOT a GitHub Actions official artifact |
| `full-suite-verified` | GitHub Actions full stress suite run with attached drill artifact |
| `official-baseline-included` | Part of Run #143 baseline |
| `pending-artifact` | No verification artifact attached |

## 1) Security / Auth

| Commit | Title | State |
|---|---|---|
| `b731052a` | Task #137 — staff-login verify-first drain doctrine | shipped, pending-artifact |
| `c8506c2a` | Task #135 — agency-login throttle drain P0 regression fix | shipped, pending-artifact |
| `e4efe529` | residual 98D P0 — don't count role-block 403s against login throttle | shipped, pending-artifact |
| `5905c8f1` | agency_portal hash field tolerance (98D Phase 2 RCA) | shipped, pending-artifact |
| `0f4881dd` | agency_portal encrypted-email lookup parity with auth.py | shipped, pending-artifact |
| `f7f21686` | Task #85 — live stress probe for peer-login throttles | shipped, pending-artifact |
| `43eded14` | Task #55 — peer staff/vendor login brute-force protection | shipped, pending-artifact |
| `b7186604` | Task #51 — cashier shift-handover password throttle | shipped, pending-artifact |
| `800c20f8` | Task #120 — cashier PIN re-auth brute-force throttle | shipped, pending-artifact |
| `8ccfbb81` | Task #124 — wire mobile cashier PIN gate into sensitive actions | shipped, pending-artifact |
| `84bcbf71` | Task #123 — cashier PIN re-probe drill report (info only) | shipped, pending-artifact |
| `3f153fe9` | Round-3 — structured Mongo/Redis throttle error logging | shipped, pending-artifact |
| `2e568749` | Round-4 — 98C test D parallel-burst rewrite (test-only) | shipped, pending-artifact |
| `67d515e7` | Round-5 — call2faVerify timeout overridable + 60s for burst (test-only) | shipped, pending-artifact |
| `388cce78` | 98C D + 98D B spec patches — RCA two P0 findings | shipped, pending-artifact |
| `e33b9aeb` | 98D B per-IP → per-account boundary (CI NAT rotation RCA) | shipped, pending-artifact |
| `4b1bb46b` | 98C cleanup hardening + operator recovery (Plan B) | shipped, pending-artifact |

**Required regression**: `98C-twofa-totp-lifecycle.spec.js`, `98D-peer-login-throttle.spec.js`, `98-mobile-cashier-surface.spec.js`. Reference: `docs/drill_reports/20260528_twofa_round5_candidate_fix_pending_verification.md`.

## 2) Finance / Idempotency

| Commit | Title | State |
|---|---|---|
| `a33036d9` | Task #60 — Idempotency-Key on folio /charge and /payment | shipped, pending-artifact |
| `1bc08daf` | Task #102 — Idempotency-Key on folio split / split-by-amount / city-ledger-transfer | shipped, pending-artifact |
| `133fedf1` | Task #80 — Idempotency-Key on folio refund / void endpoints | shipped, pending-artifact |
| `ba7e925d` | Task #81 — TTL sweep for `idempotency_keys` collection | shipped, pending-artifact |
| `cf151428` | Task #62 — transfer history report endpoint for finance reconciliation | shipped, pending-artifact |
| `26fb809a` | Task #73 — backend tests for transfer history report | shipped, targeted-verified (backend pytest) |
| `c91a3e6e` | Task #77 — backend test pinning pilot sales-lead fixture idempotency | shipped, targeted-verified (backend pytest) |

**Required regression**: `99-finance-folio-surface.spec.js`, `95-reservation-lifecycle-deep.spec.js` (city-ledger dry-run paths), plus targeted folio split/refund/void/city-ledger-transfer idempotency replay assertions.

## 3) Maintenance

| Commit | Title | State |
|---|---|---|
| `0ed0e95a` | Task #98 — fix maintenance work-order creation 500 (`_id` serialization) | shipped, pending-artifact |
| `88df4391` | Task #112 — stop sensor-triggered work orders from crashing alert endpoint | shipped, pending-artifact |
| `9b9c440f` | detailed tests for maintenance work order management | shipped, targeted-verified (backend pytest implied) |

**Required regression**: `98-maintenance-workorder-lifecycle.spec.js` end-to-end against deployed pilot.

## 4) Procurement / Inventory

| Commit | Title | State |
|---|---|---|
| `4bec3666` | Task #75 — warehouse transfer unit mismatch hard guard (422) | shipped, pending-artifact |
| `f1be9f52` | Task #20 — atomic warehouse-to-warehouse transfer endpoint | shipped, pending-artifact |
| `a7332e5a` | Task #19 — enforce supplier credit limits on PO create | shipped, pending-artifact |
| `9295a8ce` | Task #63 — UI: finance can edit supplier credit limits | shipped, pending-artifact |
| `aa9831ff` | Task #64 — warn buyers when PO is close to supplier credit ceiling | shipped, pending-artifact |
| `06dd80bb` | Task #65 — backend unit tests for supplier credit-limit guard | shipped, targeted-verified (backend pytest) |
| `9d04a617` | Task #78 — procurement dashboard credit-limit highlighting | shipped, pending-artifact |
| `d3f52c26` | Task #79 — supplier credit utilisation portfolio report | shipped, pending-artifact |
| `b0a3089a` | Task #61 — warehouse transfer screen in inventory UI | shipped, pending-artifact |
| `f3a1f5a5` | Task #74 — multi-line warehouse transfer document | shipped, pending-artifact |
| `ac4b0e71` | Task #72 — warehouse transfer history in finance UI | shipped, pending-artifact |
| `af6a2620` | Task #18 — verify warehouse transfer stress spec against live backend | shipped, targeted-verified (per task commit) |

**Required regression**: `72-warehouse-transfer-procurement.spec.js`, `70-inventory-stock.spec.js`, `71-purchasing-supplier.spec.js`.

## 5) F9C Stress Coverage Expansion

| Commit | Title | State |
|---|---|---|
| `92505463` | Task #82 — F9C 5 remaining deep stress specs vs live pilot | shipped, targeted-verified (per task commit) |
| `271dc8b6` | Task — messaging template lifecycle stress | shipped, pending-artifact |
| `1b39e240` | Task #44 — F9C spec 5: F&B BEO generator stress | shipped, pending-artifact |
| `fd1b12d3` | Task #46 — F9C spec 7: marketplace deep lifecycle stress | shipped, pending-artifact |
| `3c7ef347` | Task #42 — F9C spec 3: mobile staff surface deep stress | shipped, pending-artifact |
| `e9e762d4` | F9C — mobile cashier surface deep stress spec | shipped, pending-artifact |
| `57c0ab4e` | F9C spec 6 — sales basic lifecycle stress | shipped, pending-artifact |
| `acfa284b` | Task #52 — F9D deep stress spec for finance folio & guest-purchase | shipped, pending-artifact |
| `e1e2017b` | Task #47 — verify F9C §98 sales lifecycle vs live backend | shipped, targeted-verified |
| `eb57419f` | Task #53 — verify F&B BEO stress spec vs live backend | shipped, targeted-verified |
| `27687d0f` | Task #34 — stress suite pacing (cumulative rate under prod rate-limit) | shipped, replit-equivalent-verified (via Task #57) |
| `d47a5e30` | Task #57 — verify stress pacing fix end-to-end on deployed pilot | shipped, **replit-equivalent-verified (723 test run, NOT GH Actions artifact)** |
| `309f4e4f` | Task #48 — seed stress-tenant package for Sales quote pricing | shipped, pending-artifact |
| `6a2c9aca` | Task #58 — enable mice add-on for stress tenant + entitlement probe | shipped, pending-artifact |
| `812b7f45` | Task #87 — defer mice_sales RBAC role grant for stress admin | shipped, pending-artifact |
| `cf8f23dd` | Task #13 — pilot read-only fixtures for B2B IDOR matrix | shipped, pending-artifact |
| `a6735fce` | Task #67 — durable pilot sales lead seed for F9C §98 IDOR coverage | shipped, pending-artifact |
| `ba404e5f` | Task #33 — verify /api/pms/rooms mid-suite 0-row regression closed | shipped, targeted-verified |

**Critical clarification on Task #57 (`d47a5e30`)**: The 723-test run that
the change-summary cites is a Replit-environment equivalent of the full
suite, **not** a GitHub Actions official artifact. Commit message itself
acknowledges OAuth lacks workflow dispatch scope. This is strong
candidate evidence but it does NOT promote the baseline pointer.

## 6) F10 Mobile Coverage

| Commit | Title | State |
|---|---|---|
| `74142f05` | F10A — open mobile app test program (render-only smoke matrix) | shipped, pending-artifact |
| `af7c4a4c` | Task #119 — F10A mobile web smoke drill report (BLOCKED) | shipped, drill says blocked |
| `de46f2bf` | create mobile-web-smoke.yml (later reverted) | reverted via `d0f6c735` (OAuth workflow scope) |
| `d0f6c735` | revert all .github/workflows changes (will re-apply via GitHub web UI) | shipped, pending GH UI re-apply |
| `da421ccc` | drop mobile-web-smoke workflow (OAuth scope) | shipped |
| `8552ba75` | Task #129 — Playwright visual baseline for mobile landing | shipped, targeted-verified |
| `072408df` | Task #122 — landing page mobile layout smoke spec | shipped, pending-artifact |
| `39e14997` | Task #127 — landing page mobile redesign | shipped, pending-artifact |
| `79f90d67` | Task #128 — lighter hero image on phones | shipped, pending-artifact |
| `33815026` | Task #121 — fix landing hero text overflow on mobile | shipped, pending-artifact |
| `4b9ed5d4`, `0bb41d78`, `90918db0`, `33561a0d` | logo updates | shipped, pending-artifact |

**Required regression**: F10A mobile smoke matrix as a SEPARATE baseline track. Web PMS stress suite does NOT cover mobile.

## 7) MICE / BEO

| Commit | Title | State |
|---|---|---|
| `9da2f173` | Task #54 — printable PDF BEO export for banquet teams | shipped, pending-artifact |
| `6ad8644a` | feat(mice) — one-click BEO PDF email distribution | shipped, pending-artifact |
| `7ddbee41` | Task #84 — test new banquet BEO PDF email endpoint | shipped, targeted-verified (backend test) |
| `6e736cf1` | test(mice) — backend unit tests for BEO PDF endpoint | shipped, targeted-verified (backend test) |

**Required regression**: `98-fnb-beo-generator.spec.js` + verification that email endpoint stays in `external_dry_run` during stress (no real outbound mail).

## 8) Docs / Baseline / Tooling

| Commit | Title | State |
|---|---|---|
| `ff15eb57` | update stress test documentation with new baseline results | docs only |
| `dd95d425` | update documentation to reflect latest test run results | docs only |
| `b17c8347` | closing notes to roadmap and pointers document | docs only |
| `20801a03` | classify review items and determine pilot pre-closure risks | docs only |
| `b5fb1c21` | structured triage backlog for P2 and REVIEW items | docs only |
| `8f210d2c` | map out application test coverage gaps and report findings | docs only |
| `8983b82d` | docs(F9/F10) — daily change review + mobile coverage roadmap | docs only |
| `9fa65ad7`, `9e062a16` | F9 closure follow-ups (messaging spec + BEO tests + F10A + CI dispatch doc) | shipped, pending-artifact |
| `82d169cb` | Task #59 — targeted CI dispatch for F9D finance folio stress spec | shipped, GH UI dispatch pending |
| `bafa6ba4` | post-stabilization review document | docs only |
| `f4e15c1e` | F8M v2 — reconcile docs after 41B verification in Run #143 GREEN | docs only |
| `6f48e71e` | background worker error handling + logging | shipped, pending-artifact |
| `1a06a931` | Task #139 — router coverage PROBES matrix CI guard | shipped, pending-artifact |
| `1b20386a` | fix duplicate import causing test suite failure | shipped, pending-artifact |
| `e325488a` | update import statements across multiple files (lint) | shipped |
| `410c5cef` | organize import statements | shipped |
| `bf5ab91f` | organize code imports | shipped |
| `5671f403` | Task #35 — restore missing Playwright headless-shell binary | shipped |
| `e06dbc01` | Task #56 — collapse callTimedWithBackoff into callTimed | shipped |
| `f769512f` | Task #76 — remove deprecated callTimedWithBackoff alias | shipped |
| `e9a8ef64` | share callApiKey helper between B2B v1 and v2 stress specs | shipped |
| `c5c6af67` | Task #28 — lock in kitchen-order idempotency_key behavior | shipped, targeted-verified (backend test) |
| `21a41ab7` | backend probes + PII detection in frontend tests | shipped |
| `ff8eed50` | new routes + security checks for test coverage | shipped |
| `73b3aea3` | query param to fetch all rooms for specific test cases | shipped |
| `21a81e76` | fix test setup to properly fetch rooms by prefix | shipped |
| `ca592672` | ci(stress) — bump timeout 60→90 (CI cancel post-warmup) | shipped |
| `d34145ca` | F8AH tur-4 — 4 deferred RCA items closed (architect Round 2 PASS) | shipped |
| `79a25149` | Task #136 — RCA + fix for run #57 stress suite failures | shipped, replit-equivalent-verified (via Task #57) |
| `af64e790` | Task #99 — fix staff notification preferences page crash | shipped, pending-artifact |
| `26f22e1a` | Task #73 — backend tests for transfer history report | shipped, targeted-verified |
| `afdd8a76` | TWOFA Round-5 candidate fix pending-verification doc | docs only (this review's predecessor) |

## Aggregated commitment status

| Domain | Shipped | Targeted-verified | Replit-eq verified | GH Actions verified |
|---|---:|---:|---:|---:|
| Security / Auth | 17 | 0 | 0 | 0 |
| Finance / Idempotency | 7 | 2 | 0 | 0 |
| Maintenance | 3 | 1 | 0 | 0 |
| Procurement / Inventory | 12 | 2 | 0 | 0 |
| F9C Stress Coverage | 18 | 4 | 1 (Task #57) | 0 |
| F10 Mobile | 11 | 1 | 0 | 0 |
| MICE / BEO | 4 | 2 | 0 | 0 |
| Docs / Baseline / Tooling | 24 | 2 | 1 (Task #57 ref) | 0 |
| **Total (unique commits)** | **~100** | **~14** | **1** | **0** |

## Targeted regression pack — environment check

This Replit session **cannot safely execute the targeted regression
pack**:

- `playwright.stress.config.js` requires `E2E_BASE_URL` (not in
  available secrets). Setting it to the local dev backend would seed
  500 rooms against the stress tenant via `global-setup`, take ~25s
  for seed + Atlas warmup, then exercise ~94 specs against an
  unproven build — generating drift, load, and a non-representative
  artifact.
- Stress global-setup requires
  `E2E_ALLOW_DESTRUCTIVE_STRESS=true` + `E2E_EXTERNAL_DRY_RUN=true`;
  flipping these casually here violates the "destructive flags require
  explicit operator approval" gate.
- Atlas serverless cold-start budget per spec is up to 10 min; running
  the full targeted pack here would consume ~30-60 min wall clock and
  produce a Replit-environment artifact, which by the rules at the
  top of this document does NOT promote the baseline anyway.
- Honest no-fake-green doctrine: the right place to run this pack is
  either the deployed pilot via a properly seeded operator run, or
  GitHub Actions.

**Therefore no drill report is fabricated here.** No
`docs/drill_reports/20260528_targeted_regression_candidate.md` is
created. No `docs/drill_reports/20260528_f10a_mobile_smoke.md` is
created.

## Required next steps (operator-driven)

1. **Targeted regression pack** against deployed pilot, attaching one
   drill artifact per spec or one consolidated artifact:
   - `98C-twofa-totp-lifecycle.spec.js` (test D specifically — verifies Round-5 fix)
   - `98D-peer-login-throttle.spec.js`
   - `98-mobile-cashier-surface.spec.js`
   - `99-finance-folio-surface.spec.js`
   - `95-reservation-lifecycle-deep.spec.js`
   - `98-maintenance-workorder-lifecycle.spec.js`
   - `98-messaging-template-lifecycle.spec.js`
   - `98-fnb-beo-generator.spec.js`
   - `72-warehouse-transfer-procurement.spec.js`
2. **F10A mobile smoke** as separate matrix run; its baseline track is
   independent from web PMS.
3. **GitHub Actions Full Stress Suite one-shot** ONLY after targeted
   regressions are green. Requires re-applying the dispatch workflow
   via GitHub web UI (OAuth token in Replit lacks `workflow` scope —
   see `d0f6c735`, `da421ccc`).
4. **Baseline promotion** ONLY if the GitHub Actions artifact
   demonstrates ALL of:
   - `failedTests = 0`
   - `P0 = 0`
   - `P1 = 0`
   - `external_calls = []`
   - `pilot_drift = 0`
   - cleanup#2 idempotent (`deleted_total = 0`)
   - verdict ≥ **GO WITH WATCH**

   Any single deviation blocks promotion. P2/REVIEW items are NOT
   downgraded.

## Standing rules

- **No fake green.** Verbal "test yeşil döndü" without an attached
  drill output is candidate evidence at best.
- **No artifact, no baseline.** Pointer in `replit.md` stays at Run
  #143 / `3b3891d` / 2026-05-26 until a GitHub Actions full-suite
  artifact arrives and clears every gate.
- **Replit-environment runs are candidate evidence only**, regardless
  of how many tests they cover (Task #57's 723-test run included).
- **Security surfaces require real artifact evidence.** 2FA brute-force,
  peer-login throttles, cashier PIN throttle, idempotency replay
  protection — all are gated on full-suite artifact.
- **Do not claim GO if artifact says GO WITH WATCH.** Do not
  downgrade P2 or REVIEW findings to make verdict cleaner.

## Cross-references

- `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` — Run #143 baseline drill report
- `docs/drill_reports/20260528_twofa_round5_candidate_fix_pending_verification.md` — TWOFA Round-3/4/5 candidate fix detail
- `replit.md` — F8 Stress Test Series section (pointer source of truth)
- `docs/STRESS_TEST_ROADMAP.md` — roadmap including F9C and F8C coverage gaps
