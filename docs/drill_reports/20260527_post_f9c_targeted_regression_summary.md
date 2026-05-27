# Post-F9C Targeted Regression Pack — Combined Summary (2026-05-27)

> **Task #117.** Pre-baseline evidence pack: each surface touched by the 35 post-#143 commits exercised individually against the deployed pilot backend, so any single-surface regression is caught in isolation before the full-suite GH Actions run that will promote the next official baseline.
>
> **Baseline pointer:** Run #143 (2026-05-26, commit `3b3891d`) remains the binding baseline in `replit.md` / `docs/STRESS_TEST_ROADMAP.md`. This pack does **not** move the pointer.

## 1) Run conditions

| Field | Value |
|---|---|
| Date (UTC) | 2026-05-27 |
| Runner | Replit task agent — workflow `Post-F9C Pack` (`bash .local/run_post_f9c_pack.sh`) |
| Deployed backend | `$E2E_BASE_URL` = `https://emergent-yeni-uygulama-1.replit.app` (warmed via `/health` → `/health/ready` → `/api/health`) |
| Branch / commit | task isolation branch (post-#143 cumulative HEAD) |
| Stress tenant | `E2E_STRESS_TENANT_ID=23377306-…-50e243c0` (≠ `PILOT_TENANT_ID=5bad4a34-…-1b7375a9cf` — fail-closed gate enforced by globalSetup) |
| Playwright config | `frontend/playwright.stress.config.js` (`workers=1`, `retries=0`, per-test timeout 180s, full markdown reporter) |
| Env knobs | `E2E_ALLOW_DESTRUCTIVE_STRESS=true`, `E2E_EXTERNAL_DRY_RUN=true`, `DISABLE_EXPO_PUSH=1`, `E2E_ROOM_COUNT=500` |
| Pre-flight | `node --check` PASS on all 11 spec files; backend `/health` 200 in <1 s |
| Per-spec teardown | each spec ran its own globalSetup (seed 500-room dataset) + globalTeardown (cleanup#1 → cleanup#2 idempotent + pilot drift snapshot). 11 independent seed prefixes — no cross-spec leakage. |
| Pilot residue script | `backend/scripts/cleanup_e2e_pilot_residue.py` not run here — its target is the `E2E_…` business-flow residue in the pilot DB and it needs MongoDB access from inside the deployed runtime. In this pack, cleanup integrity is proven by the per-spec teardown snapshots below (cleanup#1 OK, cleanup#2 deleted_total=0, pilot drift=0). |

## 2) Per-spec results

| # | Spec | Tests | Failed | PASS / FAIL / REVIEW / SKIP | P0 / P1 / P2 / P3 | external_calls | pilot drift | cleanup#1 | cleanup#2 idempotent | Duration | Verdict |
|---|---|---:|---:|---|---|---|---:|---|:---:|---:|---|
| 1 | `98-maintenance-workorder-lifecycle.spec.js` | 13 | 0 | 17 / 0 / 2 / 0 | 0 / 0 / 2 / 0 | `[]` | 0 | 8154 deleted | ✅ | 154.5s | **GO WITH WATCH** |
| 2 | `98-messaging-template-lifecycle.spec.js`    | 20 | 0 | 36 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | `[]` | 0 | 8154 deleted | ✅ |  81.8s | **GO** |
| 3 | `98-mobile-staff-surface.spec.js`            | 14 | 0 | 20 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | `[]` | 0 | 8154 deleted | ✅ |  68.5s | **GO** |
| 4 | `98-mobile-cashier-surface.spec.js`          | 15 | **1** | 14 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | `[]` | 0 | 8154 deleted | ✅ | 244.4s | **NO-GO** |
| 5 | `98-fnb-beo-generator.spec.js`               | 14 | 0 | 20 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | `[]` | 0 | 8154 deleted | ✅ |  81.8s | **GO** |
| 6 | `98-sales-basic-lifecycle.spec.js`           | 13 | 0 | 18 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | `[]` | 0 | 8154 deleted | ✅ |  70.2s | **GO** |
| 7 | `98-marketplace-deep-lifecycle.spec.js`      | 14 | 0 | 14 / 0 / 3 / 1 | 0 / 0 / 3 / 0 | `[]` | 0 |    2 deleted | ✅ |  69.7s | **GO WITH WATCH** |
| 8 | `99-finance-folio-surface.spec.js`           | 16 | 0 | 25 / 0 / 5 / 1 | 0 / 0 / 2 / 0 | `[]` | 0 | 8154 deleted | ✅ |  81.9s | **GO WITH WATCH** |
| 9 | `98-pos-deep-lifecycle.spec.js`              | 11 | 0 | 33 / 0 / 1 / 0 | 0 / 0 / 1 / 0 | `[]` | 0 | 8154 deleted | ✅ | 110.6s | **GO WITH WATCH** |
| 10 | `98-pos-kds-inventory.spec.js`              | 11 | 0 | 40 / 0 / 0 / 0 | 0 / 0 / 2 / 0 | `[]` | 0 | 8154 deleted | ✅ | 104.1s | **GO WITH WATCH** |
| 11 | `72-warehouse-transfer-procurement.spec.js` |  6 | 0 | 21 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | `[]` | 0 | 8154 deleted | ✅ | 110.0s | **GO** |
| — | **Totals** | **147** | **1** | **258 / 0 / 11 / 2** | **0 / 0 / 10 / 0** | `[]` × 11 | 0 × 11 | OK × 11 | ✅ × 11 | 1177.5 s | — |

**Per-spec drill reports:**
- `docs/drill_reports/20260527_stress_98_maintenance_workorder_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_messaging_template_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_mobile_staff_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_mobile_cashier_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_fnb_beo_generator_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_sales_basic_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_marketplace_deep_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_finance_folio_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_pos_deep_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_pos_kds_inventory_targeted_post_f9c.md`
- `docs/drill_reports/20260527_stress_98_warehouse_transfer_targeted_post_f9c.md`

## 3) Doctrine enforcement

| Invariant | Required | Observed | Status |
|---|---|---|---|
| `external_calls_made = []` | yes (every spec) | `[]` on every spec (re-asserted post-batch via reporter snapshot) | ✅ PASS — 11/11 |
| `pilot_drift = 0` | yes (every spec) | `baseline_bookings=30 after_bookings=30 drift=0` on every spec | ✅ PASS — 11/11 |
| Cleanup idempotent | cleanup#2 deleted_total=0 | `0` on every spec (10 200 — 13 000 ms idempotent re-run cost only) | ✅ PASS — 11/11 |
| `failedTests = 0` | yes | 0 on 10/11 specs; **1 on `98-mobile-cashier-surface`** | ❌ FAIL on 1 spec → flagged for backend follow-up |
| `P0 = 0` | yes | 0 on every spec | ✅ PASS — 11/11 |
| `P1 = 0` | yes | 0 on every spec | ✅ PASS — 11/11 |
| No fake PASS / no skip-as-pass / no P2 downgrade | yes | All 10 P2 findings reported as P2; failing test surfaced honestly as NO-GO; no test annotated REVIEW-as-passing-equivalent | ✅ PASS — 11/11 |

## 4) Single failing test — root cause + follow-up

**Spec:** `98-mobile-cashier-surface.spec.js`
**Test:** `L) PIN brute-force throttle probe` (`line 371`)
**Failure mode:** Playwright test timeout exceeded 180 000 ms while looping wrong-PIN attempts against `POST /api/cashier/peer-verify` waiting for the throttle to trip 429. All other 14 tests in this spec passed; teardown still ran cleanly (cleanup idempotent, pilot drift=0, external_calls=[]).

**Why this is consistent with prior evidence, not a fresh regression:**
- The same surface failed in F9C pre-baseline drill `docs/drill_reports/20260527_stress_98_mobile_cashier_verify.md`: *"PIN brute-force gate — 7 wrong creds = 7×401, no 429 throttle on financial gate."*
- Task #51 introduced the *handover* peer-password brute-force throttle (`CASHIER_HANDOVER_USER` + `CASHIER_HANDOVER_IP`, 15-min window, Mongo-backed) which is verified by `98D-peer-login-throttle.spec.js`. The mobile **PIN** gate on `/api/cashier/peer-verify` is a separate code path that does not yet share the same throttle wiring.
- The doctrine forbids softening: this stays NO-GO on this spec until backend wires the same `auth_throttle.SlidingWindow` pattern into `peer-verify` so the test gets a deterministic 429 inside 180 s.

**Doctrine action:** flag for a new backend Project Task — *"Wire brute-force throttle into cashier peer-verify PIN gate"*. Until that lands, `98-mobile-cashier-surface.spec.js` is **NOT** ready for full-suite inclusion as a green spec; the other 10 specs **ARE** ready.

## 5) Spec inclusion status for the next full-suite run

| Spec | Ready for full-suite inclusion |
|---|---|
| `98-maintenance-workorder-lifecycle` | ✅ ready (GO WITH WATCH, 2 P2 informational) |
| `98-messaging-template-lifecycle`    | ✅ ready (GO) |
| `98-mobile-staff-surface`            | ✅ ready (GO) |
| `98-mobile-cashier-surface`          | ❌ blocked — backend follow-up needed for PIN throttle wiring |
| `98-fnb-beo-generator`               | ✅ ready (GO) |
| `98-sales-basic-lifecycle`           | ✅ ready (GO) |
| `98-marketplace-deep-lifecycle`      | ✅ ready (GO WITH WATCH, 3 P2 informational — `marketplace/inventory` + `purchase-orders` POST returning 404 on this tenant; same finding as historical verify report) |
| `99-finance-folio-surface`           | ✅ ready (GO WITH WATCH, 2 P2 informational) |
| `98-pos-deep-lifecycle`              | ✅ ready (GO WITH WATCH, 1 P2 informational) |
| `98-pos-kds-inventory`               | ✅ ready (GO WITH WATCH, 2 P2 informational) |
| `72-warehouse-transfer-procurement`  | ✅ ready (GO) |

## 6) Honest accounting / scope discipline

- ✅ Each of the 11 specs really ran against the deployed pilot backend (warm-up + login + 500-room seed evidence in each per-spec output under `.local/post_f9c_logs/`).
- ✅ Every spec was assigned a unique `STRESS_REPORT_TAG` so per-spec drill reports do not overwrite each other.
- ✅ Stress tenant ≠ pilot tenant verified before any write; pilot booking baseline=30 unchanged on every spec.
- ✅ Doctrine reported honestly: 10 GREEN, 1 NO-GO. No softening, no skip-as-pass, no P2 demotion.
- ⛔ Out-of-scope per task header (not done here): promoting a new official baseline, F10A mobile smoke, modifying spec sources. The next baseline declaration remains gated on the separate "Post-F9C full-suite GH Actions baseline run" Project Task.
