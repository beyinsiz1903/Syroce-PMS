# Post-F9C targeted — 98-maintenance-workorder-lifecycle — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-27T14:36:34.636Z · Tag: `98_maintenance_workorder_targeted_post_f9c`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 13 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 17 / 0 / 2 / 0 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 2 / 0 |
| Süre | 154.5s |
| Final verdict | **GO WITH WATCH** — P2=2 REVIEW=2 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779892680878_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=62.5 insert=23309.6 total=23372.1
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=8154 ms=12544.6
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=10218.3 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| maintenance_workorder | 17 | 0 | 2 | 0 | 19 |

## 5) P0/P1/P2/P3 Severity Triage

### P2 (2)
- **[maintenance_workorder]** assets POST non-2xx status=422
  - Test: `stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › F) POST+GET /api/maintenance/assets`
  - Detay: body={"detail":[{"type":"missing","loc":["body","name"],"msg":"Field required","input":{"asset_tag":"E2E_STRESS_F7_1779892680878_-ASSET-1779892718389","category":"HVAC","location":"Stress Test Lab","descri
- **[maintenance_workorder]** plans POST non-2xx status=422
  - Test: `stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › G) POST+GET /api/maintenance/plans`
  - Detay: 

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| maintenance_workorder | A_create | 1 | 520 | 520 | 520 | 520 |

## 7) Bulgular (REVIEW + SKIP detail)

**FAIL adım yok.** PASS / REVIEW / SKIP sınıflandırması üstteki tabloda.

### REVIEW (2)
- **[maintenance_workorder]** F_asset_post — -
- **[maintenance_workorder]** G_plan_post — -

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
| 1 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.7s |
| 2 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › A) Create work order — stress-tenant scoped | ✅ passed | 2.0s |
| 3 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › B) List + filter by status=open | ✅ passed | 2.0s |
| 4 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › C+D) Lifecycle: open → in_progress → completed | ✅ passed | 2.0s |
| 5 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › E) GET /api/maintenance/tasks read-only | ✅ passed | 0.5s |
| 6 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › F) POST+GET /api/maintenance/assets | ✅ passed | 0.9s |
| 7 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › G) POST+GET /api/maintenance/plans | ✅ passed | 1.0s |
| 8 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › H) GET /api/maintenance/repeat-issues read-only | ✅ passed | 0.6s |
| 9 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › I) GET /api/maintenance/sla-metrics read-only | ✅ passed | 0.5s |
| 10 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › J) IDOR: cross-tenant PATCH → no mutation | ✅ passed | 0.5s |
| 11 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › K) Anonymous (headerless) GET → 401/403 | ✅ passed | 0.3s |
| 12 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.9s |
| 13 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › N) Invariant: pilot drift — booking-count baseline + prefix scan | ✅ passed | 0.9s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

⚠️  **GO WITH WATCH → F8 (operasyonel stress senaryoları)** — REVIEW/P2 maddeleri sonraki turda izlenecek.
