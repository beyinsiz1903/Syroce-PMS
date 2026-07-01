# Stress E2E (98_mobile_staff_verify) — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-27T13:12:03.337Z · Tag: `98_mobile_staff_verify`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 14 |
| Başarısız test | 1 |
| Adım PASS / FAIL / REVIEW / SKIP | 4 / 0 / 0 / 0 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 0 / 0 |
| Süre | 60.3s |
| Final verdict | **NO-GO** — failedTests=1, FAIL adım=0 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779887528867_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=77.9 insert=20893.5 total=20971.4
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=8157 ms=11929.2
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=10020 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| mobile_staff | 4 | 0 | 0 | 0 | 4 |

## 5) P0/P1/P2/P3 Severity Triage

**Hiç finding yok.** Tüm spec'ler kritik bulgu üretmedi (pilot drift=0, business-rule guard'lar tutuyor, veri kaybı/leak yok).

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| mobile_staff | A_push_register | 1 | 532 | 532 | 532 | 532 |

## 7) Bulgular (REVIEW + SKIP detail)

### ❌ Test failure — stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › B) GET /api/notifications/preferences read
- File: `frontend/e2e-stress/specs/98-mobile-staff-surface.spec.js`  Süre: 1.3s
- Hata: Error: B_prefs_get 5xx status=500    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeLessThan[2m([22m[32mexpected[39m[2m)[22m  

## 7a) Broken Buttons / Wrong Business Rule (file:line + repro)

_Yok._ Tüm business-rule guard'lar ve UI etkileşimleri çalışıyor.

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
| 1 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.6s |
| 2 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › A) Register push device token — stress-tenant scoped | ✅ passed | 2.0s |
| 3 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › B) GET /api/notifications/preferences read | ❌ failed | 1.3s |
| 4 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › C) PUT /api/notifications/preferences update | ⏭️ skipped | 0.0s |
| 5 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › D) POST /api/pms/shift-handover create note | ⏭️ skipped | 0.0s |
| 6 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › E) GET /api/pms/shift-handover list + tenant scope | ⏭️ skipped | 0.0s |
| 7 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › F) GET /api/pms/shift-handover/open-count | ⏭️ skipped | 0.0s |
| 8 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › G) PATCH /api/pms/shift-handover/{id}/acknowledge | ⏭️ skipped | 0.0s |
| 9 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › H) GET /api/notifications/list read-only | ⏭️ skipped | 0.0s |
| 10 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › I) POST /api/notifications/push/unregister | ⏭️ skipped | 0.0s |
| 11 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › J) IDOR: cross-tenant PATCH ack → no mutation | ⏭️ skipped | 0.0s |
| 12 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › K) Anonymous (headerless) GET handover list → 401/403 | ⏭️ skipped | 0.0s |
| 13 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › M) Invariant: external_calls=[] for this module batch | ⏭️ skipped | 0.0s |
| 14 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › N) Invariant: pilot drift — booking baseline + push token prefix scan | ⏭️ skipped | 0.0s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

❌ **NO-GO** — F8 (operasyonel stress senaryoları) öncesi P0/P1 düzeltilmeli.
