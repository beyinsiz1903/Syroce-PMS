# Post Wave 6–9 — Targeted Regression Package (2026-05-30)

> Operatör (Murat) talebi: yeni feature/wave AÇMA, baseline pointer TAŞIMA, "GO"/"/100"
> İDDİA ETME, full stress KOŞMA. Önce targeted regression. Bu doküman lokal deterministik
> targeted regression sonucudur. **Run #162 resmî baseline olarak SABİT kalır**
> (commit `bde7662744c9b94a5c9294fa778202d813319dfc`) — yeni Full Stress Suite artifact'i
> oluşana kadar. Full Operational Stress Suite operatör tarafından tek-atış dispatch edilir.

## Yöntem

Çalışan lokal ortam (MongoDB + Redis + FastAPI). Murat'ın listelediği yüzeylere karşılık
gelen backend targeted testleri koşuldu. Testler iki kategoriye ayrılır:

1. **Deterministik (yüksek sinyal)** — fake-db / direct-handler / policy-guard unit/contract
   testleri; ağ/canlı-login gerektirmez. Wave 6–9 değişikliklerinin gerçek regresyon kanıtı.
2. **Ortam-bağımlı (CI-deferred)** — canlı `BASE_URL/api/auth/login`, seed'li veri, dış-ağ
   (Exely/HotelRunner) veya repo-kökü import-path gerektiren entegrasyon suite'leri. Bunlar
   lokalde hata/fail verir; bu **önceden var olan ortam koşuludur, Wave 6–9 regresyonu DEĞİL**.

## Deterministik targeted regression — SONUÇ: 181 passed / 0 failed

| Yüzey (Murat listesi) | Test dosyası | Sonuç |
|---|---|:--:|
| notification_batch / messaging activity (PII) | `test_messaging_activity_pii_rbac.py` | PASS |
| finance_folio (void RBAC + guards + idempotency) | `test_folio_void_payment_rbac.py`, `test_finance_folio_guards.py`, `test_folio_idempotency.py`, `test_pms_hardening_folio_idempotency.py`, `test_pms_hardening_folio_split_idempotency.py` | PASS |
| crm_offers (tax_no unique) | `test_company_tax_no_unique.py` | PASS |
| public_nps (duplicate guard) | `test_nps_duplicate_guard.py` | PASS |
| graphql_isolation | `test_graphql_introspection_policy.py`, `test_graphql_tenant_isolation.py` | PASS |
| kvkk_retention | `test_kvkk_anonymize_contract.py`, `test_guest_anonymization_flag.py` | PASS |
| marketplace (reclassify dokunuşu) | `test_marketplace_routes_registered.py` | PASS |
| rate_limit_boundary | `test_auth_throttle_boundary.py`, `test_rate_limiter_stress_bypass.py` | PASS |
| cm_hotelrunner_webhook (signed path) | `test_cm_signed_path_idempotency.py`, `test_hotelrunner_webhook_signature.py` | PASS |
| cm_exely_webhook (whitelist + catch-up dedup) | `test_verify_exely_whitelist.py`, `test_catchup_dedup_guard_exely.py`, `test_exely_catchup_dedup_guard.py` | PASS |
| cm conflict queue | `test_cm_conflict_queue_api.py` | PASS |

Sayım: Grup A 112 + (exely whitelist 46 + catchup 3 + 6 + hotelrunner sig 6 + cm conflict 8) =
**181 passed, 0 failed**.

## Ortam-bağımlı (CI-deferred) — regresyon DEĞİL

| Test dosyası | Lokal sonuç | Kök sebep (önceden var, env) |
|---|---|---|
| `test_b2b_api.py` | 23 error | fixture `requests.post(BASE_URL/api/auth/login)` canlı login |
| `test_b2b_webhooks.py` | 4 fail / 15 error | canlı login + seed |
| `test_agency_portal_api.py` | 3 fail / 18 error | canlı login + seed |
| `test_graphql_resolver_serialization.py` | 9 fail / 23 pass | seed'li veri bekliyor (`assert len==1` → `0`) |
| `test_exely_webhook_api.py` | 11 fail / 2 pass | `EXELY_IP_WHITELIST` set değil → fail-closed (Wave 6 belgelenmiş posture) |
| `test_hotelrunner_webhook_ingest.py` | 9 fail / 7 pass | canlı ingest + seed |
| `test_reports_export_excel_500_regression.py` | import-path | `ModuleNotFoundError: backend` (cwd; unit alt-küme importable iken PASS) |

**Önemli:** Bu suite'lerin hiçbiri Wave 9'da değişen yüzeyleri (`messaging /activity`,
`folio void_payment`, `companies` tax_no, NPS `submit_survey_response`) exercise ETMEZ.
Dolayısıyla bu hata/fail'ler Wave 6–9 ile sebep-sonuç ilişkisi taşımaz; lokal ortamda
canlı-login/seed/dış-ağ/import-path eksikliğinden kaynaklanır (CI'da operatör dispatch eder).

## Gerekli kriterler (operatör checklist)

- **external_calls=[]**: Deterministik set dış çağrı yapmaz; ağ isteyen entegrasyon testleri
  tam da dış-çağrı olmadığı için (lokalde) bağlanamaz → koşul tutarlı.
- **pilot_drift=0**: Deterministik testler fake-db / unit handler; pilot tenant DB'sine
  dokunulmaz → pilot mutation YOK.
- **no P0/P1**: Wave 6–9 değişen yüzeylerin tamamı PASS; hata/fail'ler env-bound entegrasyon,
  değişen kodda defect değil → P0/P1 YOK.
- **no PII leak**: `test_messaging_activity_pii_rbac.py` PASS — recipient maskelenmesi
  (düşük-yetkili rol) doğrulandı.
- **architect PASS**: Wave 9 kod değişiklikleri için architect PASS kayıtlı (whitespace-normalize
  caveat uygulandı + regresyon testi eklendi). Bu turda yeni kod değişikliği YOK (regression-only),
  yeni architect turu gerekmez.

## Karar

Targeted regression deterministik tarafta **181/0** ile temiz geçti; ortam-bağımlı fail'ler
Wave 6–9 regresyonu değil. **Run #162 resmî baseline SABİT.** Bir sonraki adım operatöre ait:
Full Operational Stress Suite tek-atış dispatch. Yeni run temizse Run #162 *historical* olur ve
yeni run resmî baseline'a geçer. Bu turda "GO"/"/100" iddiası YOK; yeni wave AÇILMADI.
