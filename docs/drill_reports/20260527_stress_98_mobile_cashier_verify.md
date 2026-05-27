# Stress E2E (98_mobile_cashier_verify) — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-27T13:05:55.577Z · Tag: `98_mobile_cashier_verify`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 15 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 25 / 0 / 1 / 0 |
| P0 / P1 / P2 / P3 finding | 0 / 1 / 0 / 0 |
| Süre | 75.5s |
| Final verdict | **NO-GO** — P1 finding=1 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779887161064_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=76.7 insert=18393 total=18469.7
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=8154 ms=11396.2
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=10051.7 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| mobile_cashier | 25 | 0 | 1 | 0 | 26 |

## 5) P0/P1/P2/P3 Severity Triage

### P1 (1)
- **[mobile_cashier]** Cashier handover PIN/password gate has NO brute-force throttle
  - Test: `stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › L) PIN brute-force throttle probe`
  - Detay: 7 wrong-credential attempts produced statuses=[401,401,401,401,401,401,401]; expected 429 by attempt 7. Financial gate must rate-limit.

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| mobile_cashier | C_charge | 1 | 727 | 727 | 727 | 727 |
| mobile_cashier | D_refund | 1 | 726 | 726 | 726 | 726 |
| mobile_cashier | G_close_shift | 1 | 621 | 621 | 621 | 621 |
| mobile_cashier | B_open_shift | 1 | 620 | 620 | 620 | 620 |
| mobile_cashier | I_mobile_daily | 1 | 563 | 563 | 563 | 563 |
| mobile_cashier | E_x_report | 1 | 527 | 527 | 527 | 527 |
| mobile_cashier | F_txns | 1 | 527 | 527 | 527 | 527 |
| mobile_cashier | A_current_shift | 1 | 520 | 520 | 520 | 520 |
| mobile_cashier | H_z_report | 1 | 514 | 514 | 514 | 514 |

## 7) Bulgular (REVIEW + SKIP detail)

**FAIL adım yok.** PASS / REVIEW / SKIP sınıflandırması üstteki tabloda.

### REVIEW (1)
- **[mobile_cashier]** L_pin_throttle — no throttle observed; statuses=[401,401,401,401,401,401,401]

## 7a) Broken Buttons / Wrong Business Rule (file:line + repro)

### 🖱️ Broken Buttons / UI (1)
- **[P1] [mobile_cashier] Cashier handover PIN/password gate has NO brute-force throttle** — `frontend/e2e-stress/specs/98-mobile-cashier-surface.spec.js:371`
  - Test: `stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › L) PIN brute-force throttle probe`
  - Repro: 7 wrong-credential attempts produced statuses=[401,401,401,401,401,401,401]; expected 429 by attempt 7. Financial gate must rate-limit.

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
| 1 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.7s |
| 2 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › A) GET /api/cashier/current-shift | ✅ passed | 1.0s |
| 3 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › B) POST /api/cashier/open-shift | ✅ passed | 2.1s |
| 4 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › C) POST /api/cashier/manual-transaction (charge) | ✅ passed | 2.2s |
| 5 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › D) POST /api/cashier/manual-transaction (refund) | ✅ passed | 2.2s |
| 6 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › E) GET /api/cashier/x-report | ✅ passed | 0.5s |
| 7 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › F) GET /api/cashier/shift/{id}/transactions | ✅ passed | 0.5s |
| 8 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › L) PIN brute-force throttle probe | ✅ passed | 6.1s |
| 9 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › G) POST /api/cashier/close-shift | ✅ passed | 2.1s |
| 10 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › H) GET /api/cashier/z-report/{shift_id} | ✅ passed | 0.5s |
| 11 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › I) GET /api/finance/mobile/daily-collections | ✅ passed | 0.6s |
| 12 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › J) IDOR: cross-tenant shift txn read → no leak | ✅ passed | 0.6s |
| 13 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › K) Anonymous (headerless) GET → 401/403 | ✅ passed | 0.3s |
| 14 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › M) Invariant: external_calls=[] for this module batch | ✅ passed | 1.0s |
| 15 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › N) Invariant: pilot drift — booking baseline + cashier shift scan | ✅ passed | 1.5s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

❌ **NO-GO** — F8 (operasyonel stress senaryoları) öncesi P1 düzeltilmeli (acceptance contract: P0=P1=0).
