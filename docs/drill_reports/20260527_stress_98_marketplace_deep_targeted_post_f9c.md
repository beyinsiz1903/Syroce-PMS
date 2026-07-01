# Post-F9C targeted — 98-marketplace-deep-lifecycle — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-27T14:48:22.356Z · Tag: `98_marketplace_deep_targeted_post_f9c`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 14 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 14 / 0 / 3 / 1 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 3 / 0 |
| Süre | 69.7s |
| Final verdict | **GO WITH WATCH** — P2=3 REVIEW=3 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779893307714_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=78 insert=18160.7 total=18238.7
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=2 ms=10226.8
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=9980 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| marketplace | 14 | 0 | 3 | 1 | 18 |

## 5) P0/P1/P2/P3 Severity Triage

### P2 (3)
- **[marketplace]** inventory non-200 status=404
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › F) Inventory check — GET marketplace/inventory`
  - Detay: 
- **[marketplace]** purchase-orders POST non-2xx status=404
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › H) Order place — POST purchase-orders`
  - Detay: body={"detail":"Not Found"}
- **[marketplace]** J1 unexpected status=422
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › J) IDOR: cross-tenant probes → no mutation / no leak`
  - Detay: probe=bogus_tid_fallback

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| marketplace | H_order | 1 | 710 | 710 | 710 | 710 |
| marketplace | A_publish | 1 | 707 | 707 | 707 | 707 |

## 7) Bulgular (REVIEW + SKIP detail)

**FAIL adım yok.** PASS / REVIEW / SKIP sınıflandırması üstteki tabloda.

### REVIEW (3)
- **[marketplace]** F_inventory — -
- **[marketplace]** perf:H_order — n=1 p50=710ms p95=710ms max=710ms avg=710ms
- **[marketplace]** H_order — -

### SKIP (1)
- **[marketplace]** I_cancel — no_po_created

## 7a) Broken Buttons / Wrong Business Rule (file:line + repro)

### ⚖️ Wrong Business Rule (2)
- **[P2] [marketplace] inventory non-200 status=404** — `frontend/e2e-stress/specs/98-marketplace-deep-lifecycle.spec.js:314`
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › F) Inventory check — GET marketplace/inventory`
  - Repro: -
- **[P2] [marketplace] purchase-orders POST non-2xx status=404** — `frontend/e2e-stress/specs/98-marketplace-deep-lifecycle.spec.js:364`
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › H) Order place — POST purchase-orders`
  - Repro: body={"detail":"Not Found"}

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
| 1 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 2.3s |
| 2 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › A) Publish listing — stress-tenant opt-in | ✅ passed | 3.1s |
| 3 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › B) Read listing — verify tenant scope | ✅ passed | 1.2s |
| 4 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › C) Update listing — PUT changes apply | ✅ passed | 1.2s |
| 5 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › D) Unpublish listing — DELETE sets is_listed=false | ✅ passed | 1.8s |
| 6 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › E) Re-publish after unpublish — lifecycle idempotency | ✅ passed | 2.2s |
| 7 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › F) Inventory check — GET marketplace/inventory | ✅ passed | 0.7s |
| 8 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › G) Vendor profile — GET marketplace/suppliers | ✅ passed | 0.8s |
| 9 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › H) Order place — POST purchase-orders | ✅ passed | 2.2s |
| 10 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › I) Order cancel — POST purchase-orders/{id}/reject | ⏭️ skipped | 0.0s |
| 11 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › J) IDOR: cross-tenant probes → no mutation / no leak | ✅ passed | 0.9s |
| 12 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › K) Anonymous (headerless) GET listings/me → 401/403 | ✅ passed | 0.3s |
| 13 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.8s |
| 14 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › N) Invariant: pilot drift — booking baseline + pilot marketplace prefix scan | ✅ passed | 1.6s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

⚠️  **GO WITH WATCH → F8 (operasyonel stress senaryoları)** — REVIEW/P2 maddeleri sonraki turda izlenecek.
