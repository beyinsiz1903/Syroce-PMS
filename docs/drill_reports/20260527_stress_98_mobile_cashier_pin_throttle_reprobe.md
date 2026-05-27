# Targeted re-probe — 98-mobile-cashier-surface · L) PIN brute-force throttle — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`).
> Run tag: `98_mobile_cashier_pin_throttle_reprobe` · Task #123 deliverable.
> Spec: `frontend/e2e-stress/specs/98-mobile-cashier-surface.spec.js` (tests Setup, L, M, N).
> Target: `https://emergent-yeni-uygulama-1.replit.app` (deployed pilot).

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 4 (Setup + L + M + N) |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 5 / 0 / 1 / 0 |
| P0 / P1 / P2 / P3 finding | 0 / 1 / 0 / 0 |
| Süre | 72.5 s (reporter) / ~75 s (yarn) |
| Final verdict | **NO-GO** — Task #120's `/api/cashier/peer-verify` not yet deployed to pilot. |

## 2) Seed / cleanup / pilot drift

- Seed prefix: `E2E_STRESS_F7_1779894710304_` · room_count=500 · counts:
  rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500.
- `external_calls_made`: `[]` (M invariant PASS).
- Cleanup#1: deleted_total=8154 (ms=12823.9).
- Cleanup#2 (idempotent re-run): deleted_total=0 (ms=10413.5) → idempotent=true.
- Pilot drift: baseline_bookings=30 / after_bookings=30 → **drift=0** (N invariant PASS).

## 3) Test L — PIN brute-force probe vs deployed pilot

The probe sent 11 sequential `POST /api/cashier/peer-verify` calls with wrong PINs against the deployed pilot. Observed statuses:

```
[404, 404, 404, 404, 404, 404, 404, 404, 404, 404, 404]
```

Independent curl confirms the same:

```
$ curl -X POST $E2E_BASE_URL/api/cashier/peer-verify -d '{"pin":"0000"}'
HTTP 404
```

The route handler exists in the working tree (`backend/domains/pms/cashier_router.py:318` — `@router.post("/cashier/peer-verify")` with `CASHIER_PEER_VERIFY_USER` + `CASHIER_PEER_VERIFY_IP` sliding-window throttles wired in), but the deployed pilot has not been re-released since Task #120 landed. The throttle therefore cannot be exercised end-to-end against the pilot URL.

- Test L outcome: **no expect failure** (404 < 500), but `recFinding('P1', ...)` fired because `statuses.includes(429) === false`.
- Doctrine: skip-as-pass YOK — the spec correctly surfaces this as a real P1 in the run-level finding tally rather than masking it.

## 4) Severity triage

### P1 (1)
- **[mobile_cashier]** Cashier peer-verify PIN gate has NO brute-force throttle on the deployed pilot.
  - Test: `stress › 98-mobile-cashier-surface.spec.js › L) PIN brute-force throttle probe`
  - Root cause: endpoint returns 404 on `$E2E_BASE_URL` (deploy not yet rolled out). Working-tree code wires the throttle correctly.
  - Resolution path: deploy current `main` → re-run this targeted spec → expect statuses to end in `429`, finding to drop to 0.

## 5) Invariants

| Invariant | Result |
|---|---|
| external_calls=[] for this module batch (M) | ✅ PASS |
| pilot drift = 0 (N) | ✅ PASS — baseline_bookings=30, after_bookings=30 |
| Cleanup idempotent (teardown #2) | ✅ PASS — deleted_total=0 on re-run |

## 6) Test inventory

| # | Test | Outcome | Süre |
|---:|---|---|---:|
| 1 | Setup: stress token + module probe + pilot baseline | ✅ passed | 2.6 s |
| 2 | L) PIN brute-force throttle probe | ✅ passed (with P1 finding recorded) | 6.7 s |
| 3 | M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.9 s |
| 4 | N) Invariant: pilot drift — booking baseline + cashier shift scan | ✅ passed | 1.5 s |

## 7) Promotion decision

❌ **NOT promoted to "ready for full-suite inclusion" set in `docs/STRESS_TEST_ROADMAP.md`.**

Acceptance contract for Task #123 requires test L to observe a `429` from the deployed pilot. The pilot currently returns `404`, so the throttle is not provable end-to-end. The spec stays in the targeted-run set until the pilot is redeployed with Task #120's `/api/cashier/peer-verify` handler, at which point this drill must be re-run; on a clean PASS (statuses ending in 429, P1=0) the spec can be promoted in the same change.

## 8) Artifact paths

- Auto-generated reporter file: `docs/drill_reports/20260527_stress_f7_scaffold.md` (raw reporter output for this run).
- HTML report: `frontend/playwright-stress-report/`
- Traces / videos / screenshots: `frontend/test-results-stress/`
