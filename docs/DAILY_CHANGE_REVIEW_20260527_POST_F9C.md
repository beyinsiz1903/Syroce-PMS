# Daily Change Review — 2026-05-27 · POST-F9C Stabilization Lens

> **Scope:** All commits merged on `main` **after** the Run #143 official baseline (`3b3891d`, 2026-05-26), grouped by category per Murat post-F9C review.
> **Companion doc:** `docs/DAILY_CHANGE_REVIEW_20260527.md` (per-commit ledger, 35 commits, risk + coverage status).
> **Method:** `git log 3b3891d..HEAD --oneline` enumerated; categorisation from commit subject + Task # mapping.
> **Doctrine reminders:** fake PASS yok · skip-as-pass yok · P2/REVIEW downgrade yok · `external_calls=[]` · `pilot_drift=0` · destructive POST yok.

---

## 1) Baseline status (binding)

| Item | Status | Notes |
|---|---|---|
| **Official baseline** | ✅ Run #143 (2026-05-26, commit `3b3891d`) — 84 spec / 556 test GREEN GO WITH WATCH | **Unchanged.** Pointer in `replit.md` Gotchas remains Run #143. |
| **Candidate evidence** | ⚠️ Task #57 Replit-equivalent 723-test full suite (commit `d47a5e30`, 41.3 min, `workers=1`, `destructive_stress=true`, `external_dry_run=true`, pacing fix verified) | **NOT an official baseline.** GH Actions dispatch was unavailable in task sandbox; result is pre-baseline candidate evidence only. |
| **Next official baseline** | ❌ BLOCKED on GH Actions full-suite artifact | Requires manual `workflow_dispatch` of `.github/workflows/stress.yml` from GitHub UI; artifact + summary attached to drill report before baseline pointer moves. |
| **Pilot mutation budget** | ✅ 0 (all targeted verifies dry-run + cleanup idempotent) | F9C live drills (Task #82) used non-destructive probes against pilot. |

---

## 2) Post-#143 commits grouped by category

### 2.1 — Stress spec additions (F9 sprint test coverage)

| Commit | Task | Spec / Surface |
|---|---|---|
| `271dc8b6` | — | Messaging template lifecycle stress (`98-messaging-template-lifecycle.spec.js`, 1087 satır) |
| `fd1b12d3` | #46 | Marketplace deep lifecycle (`98-marketplace-deep-lifecycle.spec.js`, 624 satır) |
| `1b39e240` | #44 | F&B BEO generator (`98-fnb-beo-generator.spec.js`, 635 satır) |
| `e9e762d4` | — | Mobile cashier surface (`98-mobile-cashier-surface.spec.js`, 747 satır) |
| `3c7ef347` | #42 | Mobile staff surface (`98-mobile-staff-surface.spec.js`, 647 satır) |
| `57c0ab4e` | — | Sales basic lifecycle (`98-sales-basic-lifecycle.spec.js`, 698 satır) |
| `9b9c440f` | — | Maintenance work order lifecycle (`98-maintenance-workorder-lifecycle.spec.js`, 522 satır) |
| `acfa284b` | #52 | F9D finance folio & guest-purchase deep (`99-finance-folio-surface.spec.js`, 826 satır) |
| `21a41ab7` | — | Backend probes + PII detection (F9B `97-backend-router-coverage-probe.spec.js`) |
| `ff8eed50` | — | F9A smoke matrix routes + security checks extension |
| `f7f21686` | #85 | Live stress probe for peer-login throttles |
| `c91a3e6e` | #77 | Backend test pinning sales-lead fixture idempotency |
| `26f22e1a` | #73 | Backend tests for transfer history report |
| `06dd80bb` | #65 | Backend unit tests for supplier credit-limit guard |
| `6e736cf1` | — | Backend unit tests for BEO PDF endpoint |
| `c5c6af67` | #28 | Kitchen-order idempotency_key behaviour lock-in |

### 2.2 — Backend hardening (defect / 500 fixes)

| Commit | Task | Fix |
|---|---|---|
| `e325488a` | — | ruff `I001` import sort across 7 backend files (CI lint) |
| `6f48e71e` | — | `TransientFailureTracker` across 11 background workers (Sentry noise reduction, architect Round-2 PASS) |
| `0ed0e95a` | #98 | `POST /api/maintenance/work-orders` 500 fix — strip Mongo `_id` from insert payload before JSON return |
| `af64e790` | #99 | `GET /api/notifications/preferences` 500 fix — projection cleanup; F9C mobile-staff spec was hard-failing this |
| `88df4391` | #112 | Sensor-triggered auto-create work order 500 fix — same `_id` leak pattern as #98 |
| `812b7f45` | #87 | Defer `mice_sales` RBAC role grant for stress admin (entitlement probe fail-fast) |
| `6a2c9aca` | #58 | Enable MICE add-on for stress tenant + fail-fast entitlement probe |

### 2.3 — Finance / idempotency hardening (real money safety)

| Commit | Task | Surface |
|---|---|---|
| `a33036d9` | #60 | Idempotency-Key on folio `/charge` and `/payment` |
| `133fedf1` | #80 | Idempotency-Key on folio refund / void-charge / void-payment (cashier double-click + network retry guard) |
| `1bc08daf` | #102 | Idempotency-Key on folio split / split-by-amount / city-ledger transfer (ghost folio / duplicate transfer guard) |
| `ba7e925d` | #81 | TTL sweep for `idempotency_keys` collection (retention bound) |

> **Why this matters:** Combined, these four cover the entire folio mutation surface against retry/double-submit. Pre-#143 only existed for reservations + inventory repositories; post-#143 expansion brings folio + city-ledger parity.

### 2.4 — Security / brute-force hardening

| Commit | Task | Surface |
|---|---|---|
| `b7186604` | #51 | Cashier shift-handover peer-password brute-force throttle (`CASHIER_HANDOVER_USER` + `CASHIER_HANDOVER_IP`, 15-min window, Mongo-backed cross-instance) |
| `43eded14` | #55 | Agency portal + supplies-market vendor login brute-force protection (per-IP + per-account NFKC casefold bucket) |
| `f7f21686` | #85 | Live stress probe — cap+1 attempt expects 429 not 401, catches silent throttle wiring breaks |

### 2.5 — Procurement / inventory enterprise controls

| Commit | Task | Capability |
|---|---|---|
| `a7332e5a` | #19 | Supplier credit limit enforcement on PO create (backend hard guard) |
| `f1be9f52` | #20 | Atomic warehouse-to-warehouse transfer endpoint |
| `4bec3666` | #75 | Unit-mismatch transfer guard — 422 without `conversion_factor` (was soft warning, stocks could corrupt on kg→adet) |
| `f3a1f5a5` | #74 | Multi-line warehouse transfer document |
| `b0a3089a` | #61 | Warehouse transfer UI screen in inventory module |
| `cf151428` | #62 | Transfer history report endpoint (finance reconciliation) |
| `ac4b0e71` | #72 | Transfer history UI surface |
| `9295a8ce` | #63 | Supplier credit limit edit UI |
| `9d04a617` | #78 | Supplier-nearing-credit-limit warning widget |
| `aa9831ff` | #64 | PO credit limit projected-amount warning (`GET /api/procurement/suppliers/{id}/credit-utilisation`) |
| `d3f52c26` | #79 | Portfolio-level supplier credit utilisation report (`GET /api/procurement/credit-utilisation`) |

### 2.6 — MICE / F&B (BEO export distribution)

| Commit | Task | Capability |
|---|---|---|
| `9da2f173` | #54 | Printable PDF BEO export (weasyprint render) |
| `6ad8644a` | — | One-click BEO PDF e-mail distribution (`POST /api/mice/events/{id}/beo/email`) |
| `7ddbee41` | #84 | BEO PDF email endpoint backend tests |

### 2.7 — Mobile / F10 program kickoff

| Commit | Task | Item |
|---|---|---|
| `74142f05` | #83 | F10A mobile smoke matrix scaffold — Playwright on Expo Web bundle, Linux-CI runnable (Maestro stays for native deep flows) |
| `de46f2bf` | — | `.github/workflows/mobile-web-smoke.yml` — manual `workflow_dispatch` gate (re-applied via GitHub UI 2026-05-27) |
| `05a78b8c` | #59 | `.github/workflows/stress.yml` — targeted single-spec dispatch input (`spec_pattern`) + `DISABLE_EXPO_PUSH=1` job-wide |

### 2.8 — Stress infra (pacer, helpers, fixtures)

| Commit | Task | Change |
|---|---|---|
| `27687d0f` | #34 | Per-token sliding-window pacer in `stress-helpers.js` (suite-wide rate-limit stability, fixes 429 on lifecycle specs) |
| `e06dbc01` | #56 | Collapse `callTimedWithBackoff` into `callTimed` |
| `f769512f` | #76 | Remove deprecated `callTimedWithBackoff` alias |
| `e9a8ef64` | #14 | Share `callApiKey` helper between B2B v1 and v2 specs |
| `a6735fce` | #67 | Seed durable pilot sales lead for F9C §98 IDOR coverage |
| `309f4e4f` | #48 | Seed stress-tenant package so Sales quote step exercises real pricing |
| `cf8f23dd` | #13 | Pilot read-only fixtures for B2B IDOR matrix sample-gap |
| `5671f403` | #35 | Restore missing Playwright headless-shell binary in post-merge |
| `26fb809a` | #30 | Tag bulk-resolve side-effects with stress markers |

### 2.9 — Verification drills (pre-baseline evidence)

| Commit | Task | Drill |
|---|---|---|
| `d47a5e30` | #57 | **723-test Replit-equivalent full suite** (candidate evidence only — not GH Actions) |
| `92505463` | #82 | 5 remaining F9C deep stress specs verified against live pilot |
| `e1e2017b` | #47 | F9C Sales lifecycle spec verified |
| `eb57419f` | #53 | F&B BEO spec verified |
| `af6a2620` | #18 | Warehouse transfer spec verified |
| `ba404e5f` | #33 | `/api/pms/rooms` mid-suite 0-row regression closed |
| `4bcdc192` | — | Published your App |

### 2.10 — Docs / baseline metadata

| Commit | Item |
|---|---|
| `8983b82d` | `docs/DAILY_CHANGE_REVIEW_20260527.md` + `docs/F10_MOBILE_COVERAGE_ROADMAP.md` |
| `8f210d2c` | `docs/TEST_COVERAGE_GAP_MAP_20260527.md` |
| `ff15eb57` | `docs/STRESS_TEST_ROADMAP.md` update |
| `dd95d425` | Stress baseline doc update |
| `b17c8347` | Closing notes / roadmap pointers |
| `20801a03` | P2 / REVIEW pre-pilot risk classification |
| `b5fb1c21` | `docs/STRESS_P2_REVIEW_TRIAGE_20260526.md` backlog |
| `f4e15c1e` | F8M v2 docs reconcile after Run #143 |
| `9fa65ad7` / `9e062a16` | F9 closure follow-ups: messaging spec amendment + BEO tests + F10A + CI dispatch doc |

---

## 3) F9C spec inventory verification

All 7 F9C deep stress specs are present in `frontend/e2e-stress/specs/` and parse cleanly:

```
98-maintenance-workorder-lifecycle.spec.js   522 lines   node --check OK
98-messaging-template-lifecycle.spec.js     1087 lines   node --check OK
98-mobile-staff-surface.spec.js              647 lines   node --check OK
98-mobile-cashier-surface.spec.js            747 lines   node --check OK
98-fnb-beo-generator.spec.js                 635 lines   node --check OK
98-sales-basic-lifecycle.spec.js             698 lines   node --check OK
98-marketplace-deep-lifecycle.spec.js        624 lines   node --check OK
─────────────────────────────────────────────────────
total                                       4960 lines
```

- **F9C file delivery: COMPLETE.**
- **F9C targeted live-pilot verification: COMPLETE** for all 7 (Task #82 batch + per-spec verify drills under `docs/drill_reports/20260527_stress_98_*_verify.md`).
- **F9C inclusion in next official baseline:** PENDING GH Actions full-suite artifact.

---

## 4) Remaining baseline-promotion gap

To move the baseline pointer from Run #143 to a post-F9C run, the following must land **in this order**:

1. **Targeted regression pack** (deploy env / pilot) — each new spec individually green:
   - `98-maintenance-workorder-lifecycle.spec.js`
   - `98-messaging-template-lifecycle.spec.js`
   - `98-mobile-staff-surface.spec.js`
   - `98-mobile-cashier-surface.spec.js`
   - `98-fnb-beo-generator.spec.js`
   - `98-sales-basic-lifecycle.spec.js`
   - `98-marketplace-deep-lifecycle.spec.js`
   - `99-finance-folio-surface.spec.js`
   - `98-pos-deep-lifecycle.spec.js` + `98-pos-kds-inventory.spec.js`
   - `72-warehouse-transfer-procurement.spec.js`
   - F&B / procurement / cashier regression specs touched by post-#143 commits

2. **GH Actions full-suite official run** (`workflow_dispatch` on `.github/workflows/stress.yml` from GitHub UI):
   - `workers=1`, `destructive_stress=true`, `external_dry_run=true`, `DISABLE_EXPO_PUSH=1`
   - Acceptance: `failedTests=0`, `P0=P1=0`, `external_calls=[]`, `pilot_drift=0`, cleanup idempotent, verdict ≥ GO WITH WATCH
   - Artifact + run URL + spec count + test count quoted in drill report

3. **F10A mobile smoke** (separate drill report) — `workflow_dispatch` on `.github/workflows/mobile-web-smoke.yml` with deployed Expo Web bundle URL. Report includes route count, role-based render result, fatal console errors, PII/token leak count, auth redirect result.

4. **Post-baseline doc updates** (only after artifact in hand):
   - `docs/STRESS_TEST_ROADMAP.md` — new official baseline row
   - `docs/TEST_COVERAGE_GAP_MAP_20260527.md` — ZERO→PARTIAL transitions confirmed
   - `docs/PILOT_TRUST_NARRATIVE.md` — verified coverage line bumped
   - `replit.md` Gotchas — baseline pointer moved off Run #143

---

## 5) This-session deliverables (honest accounting)

| Deliverable | Status |
|---|---|
| This POST-F9C review doc | ✅ |
| F9C 7-spec existence + `node --check` syntax verification | ✅ |
| Targeted regression run | ❌ Cannot run from this environment (deploy + CI required) — proposed as Project Task |
| Full-suite GH Actions run | ❌ Cannot dispatch from this environment — proposed as Project Task |
| F10A mobile smoke run | ❌ Cannot run from this environment — proposed as Project Task |
| Baseline pointer move in `replit.md` | ❌ Intentionally NOT moved — gated on artifact above |
| `STRESS_TEST_ROADMAP.md` / gap map / trust narrative updates | ❌ Intentionally deferred — gated on artifact above |

---

## 6) Closing note

Run #143 remains the binding baseline. The post-#143 changeset is dense (35 commits, 7 deep stress specs, 4 finance idempotency endpoints, 3 maintenance 500 fixes, 11 procurement/inventory commits, F10A program kickoff) and architecturally sound, but the next official baseline declaration is **paused** on a single missing artifact: a GH Actions full-suite green run. The infra to dispatch it is in place (`.github/workflows/stress.yml` updated 2026-05-27 with targeted-spec input + `DISABLE_EXPO_PUSH=1` job-wide). Targeted regression and full-suite runs are proposed as separate Project Tasks (require deploy + CI access not available to the main agent here).
