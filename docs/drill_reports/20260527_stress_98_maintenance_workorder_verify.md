# Stress E2E (98_maintenance_workorder_verify) — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-27T13:00:12.866Z · Tag: `98_maintenance_workorder_verify`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 13 |
| Başarısız test | 1 |
| Adım PASS / FAIL / REVIEW / SKIP | 2 / 0 / 1 / 0 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 0 / 0 |
| Süre | 58.9s |
| Final verdict | **NO-GO** — failedTests=1, FAIL adım=0 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779886819094_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=86.3 insert=20092.2 total=20178.5
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=8154 ms=12289
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=10337.8 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| maintenance_workorder | 2 | 0 | 1 | 0 | 3 |

## 5) P0/P1/P2/P3 Severity Triage

**Hiç finding yok.** Tüm spec'ler kritik bulgu üretmedi (pilot drift=0, business-rule guard'lar tutuyor, veri kaybı/leak yok).

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| maintenance_workorder | A_create | 1 | 787 | 787 | 787 | 787 |

## 7) Bulgular (REVIEW + SKIP detail)

### ❌ Test failure — stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › A) Create work order — stress-tenant scoped
- File: `frontend/e2e-stress/specs/98-maintenance-workorder-lifecycle.spec.js`  Süre: 0.9s
- Hata: Error: A_create unexpected status=500    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeLessThan[2m([22m[32mexpected[39m[2m)[22m  

### REVIEW (1)
- **[maintenance_workorder]** perf:A_create — n=1 p50=787ms p95=787ms max=787ms avg=787ms

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
| 1 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.6s |
| 2 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › A) Create work order — stress-tenant scoped | ❌ failed | 0.9s |
| 3 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › B) List + filter by status=open | ⏭️ skipped | 0.0s |
| 4 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › C+D) Lifecycle: open → in_progress → completed | ⏭️ skipped | 0.0s |
| 5 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › E) GET /api/maintenance/tasks read-only | ⏭️ skipped | 0.0s |
| 6 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › F) POST+GET /api/maintenance/assets | ⏭️ skipped | 0.0s |
| 7 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › G) POST+GET /api/maintenance/plans | ⏭️ skipped | 0.0s |
| 8 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › H) GET /api/maintenance/repeat-issues read-only | ⏭️ skipped | 0.0s |
| 9 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › I) GET /api/maintenance/sla-metrics read-only | ⏭️ skipped | 0.0s |
| 10 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › J) IDOR: cross-tenant PATCH → no mutation | ⏭️ skipped | 0.0s |
| 11 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › K) Anonymous (headerless) GET → 401/403 | ⏭️ skipped | 0.0s |
| 12 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › M) Invariant: external_calls=[] for this module batch | ⏭️ skipped | 0.0s |
| 13 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › N) Invariant: pilot drift — booking-count baseline + prefix scan | ⏭️ skipped | 0.0s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

❌ **NO-GO** — F8 (operasyonel stress senaryoları) öncesi P0/P1 düzeltilmeli.
