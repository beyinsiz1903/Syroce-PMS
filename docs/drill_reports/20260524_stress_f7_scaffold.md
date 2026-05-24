# F7 — Stress E2E Scaffold — 20260524

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-24T13:20:17.985Z · Tag: `f7_scaffold`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 10 |
| Başarısız test | 1 |
| Adım PASS / FAIL / REVIEW / SKIP | 39 / 0 / 1 / 5 |
| P0 / P1 / P2 / P3 finding | 1 / 0 / 5 / 0 |
| Süre | 83.1s |
| Final verdict | **NO-GO** — P0 finding=1 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779628825393_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=80.2 insert=18693.2 total=18773.4
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=8152 ms=7114.4
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=6717.5 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| efatura_earsiv_dryrun | 5 | 0 | 0 | 0 | 6 |
| identity_reporting_dryrun | 11 | 0 | 1 | 0 | 13 |
| kvkk_retention | 11 | 0 | 0 | 2 | 14 |
| payment_pos_reconciliation | 12 | 0 | 0 | 3 | 16 |

## 5) P0/P1/P2/P3 Severity Triage

### P0 (1)
- **[efatura_earsiv_dryrun]** Cross-tenant invoice update IDOR
  - Test: `stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement`
  - Detay: stress_token PUT /api/invoices/4e7a47e0-19c3-4921-83f5-e54c9821a584 → 200 (PILOT tenant invoice mutated). KESIN tenant breach.

### P2 (5)
- **[identity_reporting_dryrun]** KBS_TEST_MODE prefix guard not enforced (env likely off)
  - Test: `stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS_TEST_MODE prefix guard + queue schema enforcement`
  - Detay: POST /api/kbs/queue/.../complete with no TEST- prefix → http=404. If KBS_TEST_MODE=1 expected 422 with "TEST-" mention; route reached job-not-found instead. Env state review needed.
- **[kvkk_retention]** Anonymize / hard-delete guest endpoint not surfaced
  - Test: `stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › GDPR + retention surface read-only probe`
  - Detay: Backend explicit `/api/gdpr/anonymize` veya `/api/gdpr/guest-delete` endpoint'i bulunmadı. KVKK silinme talebi şu an file-level (ID-photo) cleanup'a dayanıyor; guest profile anonymize/erase iş kuralı için endpoint kontratı gerekir. Roadmap backlog: F8AA v2.
- **[efatura_earsiv_dryrun]** InvoiceCreate schema lacks VKN/TCKN customer identity fields
  - Test: `stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement`
  - Detay: Backend `InvoiceCreate` (`backend/models/schemas/invoicing.py`) yalnız customer_name + customer_email saklıyor; Türkiye e-fatura/e-arşiv UBL pratiğinde VKN (kurumsal) ve TCKN (bireysel) zorunlu. Schema genişletilmesi roadmap backlog: F8X v2.
- **[payment_pos_reconciliation]** Payment pos_tables_list surface module-blocked
  - Test: `stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › cashier + POS read-only surface`
  - Detay: GET /api/pos/tables?limit=5 http=404 reason=endpoint_not_deployed.
- **[payment_pos_reconciliation]** Manual transaction idempotency probe skipped
  - Test: `stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › manual-transaction X-Idempotency-Key replay`
  - Detay: Cashier current-shift http=200 body.shift=null; cannot exercise X-Idempotency-Key replay without active shift.

## 6) Performance Hotspots (top 10 slowest ops, p95)

_Performans örneği yok._

## 7) Bulgular (REVIEW + SKIP detail)

### ❌ Test failure — stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement
- File: `frontend/e2e-stress/specs/98-efatura-earsiv-dryrun.spec.js`  Süre: 4.5s
- Hata: Error: cross-tenant invoice update must be 403/404    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeGreaterThanOrEqual[2m([22m[32mexpected[39m[2m)[22m  

### REVIEW (1)
- **[identity_reporting_dryrun]** kbs_test_mode_prefix_guard — http=404 (KBS_TEST_MODE likely OFF; prefix check skipped, route reached job lookup)

### SKIP (5)
- **[kvkk_retention]** idphoto_xtenant_single_delete — pilot photo harvest empty
- **[kvkk_retention]** idphoto_xtenant_bulk_delete — pilot booking harvest empty
- **[payment_pos_reconciliation]** pos_tables_list_probe — module_blocked:endpoint_not_deployed http=404
- **[payment_pos_reconciliation]** folio_cross_tenant_payment — pilot folio harvest empty
- **[payment_pos_reconciliation]** manual_txn_idempotency — no open cashier shift (http=200, shift=null); idempotency probe requires active shift.

## 7a) Broken Buttons / Wrong Business Rule (file:line + repro)

### ⚖️ Wrong Business Rule (3)
- **[P2] [identity_reporting_dryrun] KBS_TEST_MODE prefix guard not enforced (env likely off)** — `frontend/e2e-stress/specs/65-identity-reporting-kbs-jandarma-dryrun.spec.js:71`
  - Test: `stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS_TEST_MODE prefix guard + queue schema enforcement`
  - Repro: POST /api/kbs/queue/.../complete with no TEST- prefix → http=404. If KBS_TEST_MODE=1 expected 422 with "TEST-" mention; route reached job-not-found instead. Env state review needed.
- **[P0] [efatura_earsiv_dryrun] Cross-tenant invoice update IDOR** — `frontend/e2e-stress/specs/98-efatura-earsiv-dryrun.spec.js:47`
  - Test: `stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement`
  - Repro: stress_token PUT /api/invoices/4e7a47e0-19c3-4921-83f5-e54c9821a584 → 200 (PILOT tenant invoice mutated). KESIN tenant breach.
- **[P2] [payment_pos_reconciliation] Manual transaction idempotency probe skipped** — `frontend/e2e-stress/specs/98-payment-pos-reconciliation-dryrun.spec.js:165`
  - Test: `stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › manual-transaction X-Idempotency-Key replay`
  - Repro: Cashier current-shift http=200 body.shift=null; cannot exercise X-Idempotency-Key replay without active shift.

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
| 1 | stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS read-only surface + setup-info probe | ✅ passed | 4.5s |
| 2 | stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS_TEST_MODE prefix guard + queue schema enforcement | ✅ passed | 4.7s |
| 3 | stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › GDPR + retention surface read-only probe | ✅ passed | 3.5s |
| 4 | stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › ID-photo single + bulk delete cross-tenant guard | ✅ passed | 3.2s |
| 5 | stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › GDPR data-requests cross-tenant filter probe | ✅ passed | 2.2s |
| 6 | stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement | ❌ failed | 4.5s |
| 7 | stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › ERP integration sync — forbidden real provider HTTP | ⏭️ skipped | 0.0s |
| 8 | stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › cashier + POS read-only surface | ✅ passed | 4.7s |
| 9 | stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › folio payment — schema enforcement + cross-tenant IDOR | ✅ passed | 3.7s |
| 10 | stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › manual-transaction X-Idempotency-Key replay | ✅ passed | 2.3s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

❌ **NO-GO** — F8 (operasyonel stress senaryoları) öncesi P0 düzeltilmeli.
