# Post-F9C targeted — 99-finance-folio-surface — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-27T14:49:33.043Z · Tag: `98_finance_folio_targeted_post_f9c`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 16 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 25 / 0 / 5 / 1 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 2 / 0 |
| Süre | 81.9s |
| Final verdict | **GO WITH WATCH** — P2=2 REVIEW=5 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779893378533_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=82.5 insert=18056.7 total=18139.2
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=8154 ms=11489.8
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=10049.9 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| finance_folio | 25 | 0 | 5 | 1 | 31 |

## 5) P0/P1/P2/P3 Severity Triage

### P2 (2)
- **[finance_folio]** folio/create non-2xx status=409
  - Test: `stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › A0) POST /api/folio/create (open lifecycle)`
  - Detay: booking=02d1cafe-e9cc-4dad-955b-110881cc290a body={"detail":"Open folio already exists for this booking and folio type"} — constraint/RBAC likely; downstream tests continue against harvested folio.
- **[finance_folio]** folio payment POST blocked status=409
  - Test: `stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › D) POST /api/folio/{folio_id}/payment + Idempotency-Key replay`
  - Detay: stress_token payment permission yok (folio_id=8d3b9159-3fba-410d-95d9-48bc1467e488).

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| finance_folio | E_void_charge | 1 | 2332 | 2332 | 2332 | 2332 |
| finance_folio | C_charge | 1 | 1236 | 1236 | 1236 | 1236 |
| finance_folio | A0_open | 1 | 1111 | 1111 | 1111 | 1111 |
| finance_folio | B_detail | 1 | 1004 | 1004 | 1004 | 1004 |
| finance_folio | D_payment | 1 | 824 | 824 | 824 | 824 |
| finance_folio | A_list | 1 | 675 | 675 | 675 | 675 |
| finance_folio | G_guest_purchase | 1 | 630 | 630 | 630 | 630 |

## 7) Bulgular (REVIEW + SKIP detail)

**FAIL adım yok.** PASS / REVIEW / SKIP sınıflandırması üstteki tabloda.

### REVIEW (5)
- **[finance_folio]** perf:A0_open — n=1 p50=1111ms p95=1111ms max=1111ms avg=1111ms
- **[finance_folio]** A0_open — -
- **[finance_folio]** perf:D_payment — n=1 p50=824ms p95=824ms max=824ms avg=824ms
- **[finance_folio]** D_payment — -
- **[finance_folio]** perf:G_guest_purchase — n=1 p50=630ms p95=630ms max=630ms avg=630ms

### SKIP (1)
- **[finance_folio]** F_void_payment — no_created_payment_to_void

## 7a) Broken Buttons / Wrong Business Rule (file:line + repro)

### ⚖️ Wrong Business Rule (2)
- **[P2] [finance_folio] folio/create non-2xx status=409** — `frontend/e2e-stress/specs/99-finance-folio-surface.spec.js:195`
  - Test: `stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › A0) POST /api/folio/create (open lifecycle)`
  - Repro: booking=02d1cafe-e9cc-4dad-955b-110881cc290a body={"detail":"Open folio already exists for this booking and folio type"} — constraint/RBAC likely; downstream tests continue against harvested folio.
- **[P2] [finance_folio] folio payment POST blocked status=409** — `frontend/e2e-stress/specs/99-finance-folio-surface.spec.js:359`
  - Test: `stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › D) POST /api/folio/{folio_id}/payment + Idempotency-Key replay`
  - Repro: stress_token payment permission yok (folio_id=8d3b9159-3fba-410d-95d9-48bc1467e488).

## 7b) Cleanup Integrity

| Adım | Durum | Detay |
|---|---|---|
| cleanup#1 (deletion) | ✅ OK | deleted_total=n/a |
| cleanup#2 (idempotency) | ✅ idempotent | re-run deleted=n/a |
| pilot drift | ✅ drift=0 | baseline=[object Object] after=[object Object] |

_Audit logs are NEVER deleted (KVKK retention) — bu liste sadece stress-seeded business data'yı kapsar._

## 8) Test inventory

| # | Test | Outcome | Süre |
|---:|---|---|---:|
| 1 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › Setup: stress token + module probe + pilot baseline + harvest | ✅ passed | 1.9s |
| 2 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › A0) POST /api/folio/create (open lifecycle) | ✅ passed | 2.3s |
| 3 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › A) GET /api/folio/list | ✅ passed | 1.9s |
| 4 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › B) GET /api/folio/{folio_id} | ✅ passed | 2.2s |
| 5 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › C) POST /api/folio/{folio_id}/charge + Idempotency-Key replay | ✅ passed | 3.5s |
| 6 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › D) POST /api/folio/{folio_id}/payment + Idempotency-Key replay | ✅ passed | 2.0s |
| 7 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › E) POST /api/folio/{id}/void-charge/{cid} | ✅ passed | 3.5s |
| 8 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › F) POST /api/folio/{id}/payment/{pid}/void | ⏭️ skipped | 0.0s |
| 9 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › G) POST /api/guest/purchase-upsell/{booking_id} (staff token rejected) | ✅ passed | 1.8s |
| 10 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › H) GET /api/guest/purchased-upsells/{booking_id} (tenant scope) | ✅ passed | 2.7s |
| 11 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › I) IDOR: cross-tenant folio detail + mutate → all rejected | ✅ passed | 3.9s |
| 12 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › J) Anonymous GET /api/folio/list → 401/403 | ✅ passed | 0.3s |
| 13 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › K) Bogus folio id mutations → 4xx | ✅ passed | 2.9s |
| 14 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › L) Teardown: void leftover stress charges/payments | ✅ passed | 0.0s |
| 15 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › M) Invariant: external_calls=[] for this module batch | ✅ passed | 1.0s |
| 16 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › N) Invariant: pilot drift — booking baseline | ✅ passed | 0.6s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

⚠️  **GO WITH WATCH → F8 (operasyonel stress senaryoları)** — REVIEW/P2 maddeleri sonraki turda izlenecek.
