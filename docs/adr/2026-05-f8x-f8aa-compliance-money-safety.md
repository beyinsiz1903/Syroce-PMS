# ADR — F8X–F8AA Local Compliance & Money Safety Stress Pack

**Status:** Specs written + architect-fix applied (2026-05-24); full-suite verification pending.

## Architect review iteration (2026-05-24)

İlk yazımda architect NO-GO verdi: 4 spec'in IDOR ve validation probe'ları
backend request contract'larına uymadığı için 422 ile düşüp gerçek tenant
guard'ı ölçmüyordu (fake-PASS riski). Aşağıdaki fix'ler uygulandı:

- **F8X:** `InvoiceCreate` şemasında VKN/TCKN field yok — invalid VKN/TCKN
  testi yanlış kurguydu; kaldırıldı. Yerine schema-enforcement probe
  (eksik zorunlu alan → 422 PASS) + VKN/TCKN gap'i P2 REVIEW (Türkiye
  e-fatura UBL pratiğinde gerekli, schema genişletilmeli). Valid POST
  yapılmıyor çünkü `db.invoices` STRESS_COLLECTIONS sweep'inde yok
  (cleanup blind spot guard).
- **F8Y:** `KBSQueueClaim` `worker_id` zorunlu — cross-tenant claim probe
  artık schema-valid body ile çağrılıyor (validation 422 değil, tenant
  guard ölçülür). `KBS_TEST_MODE` `TEST-` prefix guard backend'te
  `/queue/{id}/complete` başında çalışıyor (DB lookup'tan ÖNCE);
  probe artık bogus job_id + `worker_id` + no-prefix `kbs_reference`
  payload ile complete endpoint'ine çarpıp prefix kontrolünü ölçer
  (422 + "TEST-" mesajı = PASS, 404 = env OFF → P2 REVIEW).
  KBSQueueEnqueue'da TC field olmadığı için eski "invalid TC" testi
  kaldırıldı; yerine bogus booking_id testi (4xx PASS).
- **F8Z:** `PaymentCreate` `payment_type` zorunlu (PaymentType enum:
  prepayment/deposit/interim/final/refund). Payload artık schema-valid
  `payment_type: 'deposit'` içeriyor → cross-tenant IDOR probe gerçek
  tenant guard'ı ölçer. `/api/cashier/current-shift` yanıtı `{shift: {...}}`
  nested shape — open-shift detection `body.shift.id` ile düzeltildi.
  `manual-transaction` header alias `X-Idempotency-Key` (eski `Idempotency-Key`
  yanlıştı); payload `direction: 'in'|'out'` + `description` zorunlu
  + `method` default cash.
- **F8AA:** `/api/checkin/online/id-photos/{photo_id}` DELETE `reason`
  query param zorunlu — eski test reason vermediği için 400 alıp PASS
  sayıyordu; cross-tenant guard ölçülmüyordu. Şimdi reason verili →
  pilot photo_id ile 404 PASS / 2xx = P0 ayrımı net. Bulk-delete payload
  `{booking_id|guest_id, reason}` (eski `{photo_ids: [...]}` yanlıştı);
  pilot booking_id harvest + stress_token + reason → backend query
  `{tenant_id: stress, booking_id: pilot}` eşleşmediği için deleted=0
  PASS; >0 = P0.
- **Genel:** Tüm 4 spec'te `try/finally` bloğu eklendi — `expect()` throw
  veya beklenmeyen hata path'inde bile `assertNoExternalCallsPostBatch`
  + `assertPilotDriftZero` invariants ZORUNLU çalışır.

### Re-review iteration 2 fix (2026-05-24)

Architect 2. turda 2 son fake-PASS riski yakaladı:

- **F8Y:** `/api/kbs/queue` backend yanıtı `{jobs: [...]}` shape; spec
  `raw.items || raw.queue || list` okuyordu → `pilotJobId` çoğunlukla
  null → cross-tenant claim probe SKIP'e düşüyordu. Fix: `raw.jobs`
  ilk önceliğe alındı.
- **F8Z:** `/api/cashier/manual-transaction` yanıtı `{ok, transaction}`
  nested; spec `r.body.id` okuyordu → 2xx'te bile id null → idempotency
  ihlali REVIEW'a düşürülüyordu. Fix: `extractTxnId` helper'ı önce
  `transaction.id`'ye bakar; ek olarak `bothOk && !idempotent` → P1
  hard finding + step status `FAIL` (REVIEW'a saklanmaz).


**Context:** 2026-05-24 GREEN baseline (commit `ee7573b3`, 68 specs,
P0=P1=0, external_calls=[], pilot_drift=0) üzerine, Türkiye otel pazarı
için pilot satışın kritik güven katmanı olan **yerel uyum + para güvenliği**
yüzeylerini stres test kapsamına almak.

## Karar

4 yeni Playwright stress spec ekleyerek mevcut Full Operational Stress
Suite'i uzat:

| ID | Spec dosyası | Modül | Hedef yüzey |
|---|---|---|---|
| F8X | `frontend/e2e-stress/specs/98-efatura-earsiv-dryrun.spec.js` | `efatura_earsiv_dryrun` | E-fatura / e-arşiv create, ERP sync (Logo/Netsis), cross-tenant invoice IDOR |
| F8Y | `frontend/e2e-stress/specs/65-identity-reporting-kbs-jandarma-dryrun.spec.js` | `identity_reporting_dryrun` | KBS queue/report, invalid TC validation, KBS_TEST_MODE prefix, cross-tenant queue claim |
| F8Z | `frontend/e2e-stress/specs/98-payment-pos-reconciliation-dryrun.spec.js` | `payment_pos_reconciliation` | Folio payment, cashier, POS read-only, manual-txn Idempotency-Key, cross-tenant folio payment IDOR |
| F8AA | `frontend/e2e-stress/specs/66-kvkk-retention-deletion-anonymization.spec.js` | `kvkk_retention` | GDPR data-requests, ID-photo delete + bulk-delete, retention settings, cross-tenant disclosure |

## Doctrine (mutlak — gevşetme yok)

Her spec aşağıdaki invariant'lara uymak ZORUNDA:

- `pilot mutation = 0` — pilot tenant yalnız read-only snapshot.
- `external_calls = []` — gerçek GİB / Emniyet / Jandarma / Iyzico /
  Stripe / Logo / Netsis / SMS / email HTTP çağrısı tetiklenmez.
- `pilot_drift = 0` — `assertPilotDriftZero` her test sonunda çalışır.
- Cleanup idempotent — yeni stress koleksiyonu OLUŞTURULMAZ; mevcut
  STRESS_COLLECTIONS havuzu yeterli (4 spec read+validate ağırlıklı,
  yalnız F8Z manual-transaction Idempotency-Key denemesi stress
  tenant cashier shift varsa POST yapar).
- `expect().toBeGreaterThanOrEqual(400)` ile cross-tenant IDOR
  hard-fail — pasif `recFinding` ile geçiştirmek YASAK.
- Eksik endpoint → `recFinding(P2, …, module-blocked, …)` + `rec(SKIP)`
  + final invariants yine çalışır. **Fake PASS YOK.**

## Endpoint discovery sonuçları

`backend/` taraması sonucunda:

- **E-fatura:** `/api/invoices` CRUD mevcut; explicit `/efatura/*` veya
  `dry_run` flag YOK. Logo/Netsis ERP connector'ları mock (`asyncio.sleep`)
  ama yine de post-batch external-calls delta=0 invariant'ı çalışır.
- **KBS:** `/api/kbs/{guests,report,queue,reports,setup-info}` mevcut;
  `KBS_TEST_MODE=1` env iken `TEST-` prefix zorunlu (backend kbs.py:806).
  Jandarma ayrı endpoint YOK — KBS surface'i ortak.
- **Payment/POS:** `/api/folio/{id}/payment`, `/api/cashier/*`,
  `/api/pos/*` mevcut; explicit `dry_run` flag YOK. Bu nedenle WRITE
  probe minimumda tutuldu (validation + IDOR + Idempotency-Key replay).
- **KVKK:** `/api/gdpr/data-requests`, `/api/checkin/online/id-photos`
  ve retention settings mevcut; explicit `anonymize` / `guest-hard-delete`
  endpoint YOK → F8AA bunu P2 REVIEW olarak kaydetti (roadmap backlog
  F8AA v2).

## Spec yapısı pattern'i

Her spec şu blokları içerir:

1. **Setup** — `pilotBookingsCount(pilot_token)` ile baseline snapshot.
2. **Read-only probes** — `withModuleProbe(endpoint)` matrix. 403/404 →
   P2 informational + SKIP, diğerleri PASS.
3. **Validation probes** — invalid input (VKN/TCKN/TC, negative amount,
   missing fields) → 4xx beklenir; aksi P1 finding.
4. **Cross-tenant IDOR probes** — pilot harvest ID → `stress_token` ile
   write attempt → 4xx zorunlu (`expect().toBeGreaterThanOrEqual(400)`),
   2xx = P0 hard-fail.
5. **Final invariants** — `assertNoExternalCallsPostBatch` + `assertPilotDriftZero`.

## Sonuç doğrulanması (next step)

Bu ADR specs-written kabul edilir. Full Operational Stress Suite
verification (commit + republish + CI green) sonraki turun sorumluluğunda.
Beklenen baseline:

- Spec count: **72** (68 + 4)
- failedTests = 0, P0 = P1 = 0
- external_calls = [], pilot_drift = 0
- cleanup idempotent
- F8X–F8AA içinde muhtemel P2 module-blocked: anonymize endpoint
  (F8AA bilinen), POS routes (F8Z) — backend deploy'a göre.

## İleri backlog

- **F8X v2:** UBL XML payload shape validation (provider connector mock
  payload assertion) — backend connector real dispatch yapmadığı için
  şu an surface yok.
- **F8Y v2:** Jandarma ayrı dispatch endpoint (KBS surface'inden ayrılırsa).
- **F8Z v2:** Iyzico/Stripe payment intent dry-run flag (backend `dry_run`
  parametresi eklenirse positive write probe açılabilir).
- **F8AA v2:** Backend `/api/gdpr/guest/{id}/anonymize` endpoint
  kontratı şart; eklendikten sonra anonymize dry-run + retention
  rule probe genişletilir.
