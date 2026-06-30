# Package C — Product Contract / Compliance REVIEW/SKIP Reduction — Inventory

> Baseline: Run #168 (current official GREEN BASELINE) — P2=57 / REVIEW=48 /
> SKIP=43 / P3=1, GO WITH WATCH. Bu doküman 8 hedef yüzeyi kod-kanıtıyla
> sınıflandırır. Doktrin: no fake-green, no broad RBAC grant, no auth weakening,
> no pilot mutation, external_calls=[]. Baseline pointer TAŞINMAZ; full stress
> KOŞTURULMADI (operatör dispatch). Kategoriler: **SAFE-FIX** (bu pakette yapıldı),
> **CONFIRM-BY-DESIGN**, **OPERATOR-ENV**, **SCOPED-FOLLOW-UP**.

## Özet sınıflandırma

| # | Hedef | Kategori | Aksiyon |
|---|---|---|---|
| 1 | e-Fatura/e-Arşiv VKN-TCKN identity | **SAFE-FIX** | `AccountingInvoiceCreateRequest.customer_tax_number` parite validator + targeted test |
| 2 | Revenue dry_run global kill-switch | SCOPED-FOLLOW-UP | tenant shadow_mode/write_enabled zaten fail-safe; global env çok-endpoint |
| 3 | B2B per-subrouter scope provisioning | SCOPED-FOLLOW-UP | yeni ürün özelliği (scope alanı + 13 router + migration); zorlanmadı |
| 4 | CRM corporate contract approval lifecycle | CONFIRM + SCOPED | agency contract state machine zaten tam; corporate-contract approval ayrı feature |
| 5 | KVKK anonymize vs hard-delete | CONFIRM-BY-DESIGN | anonymize-only + audit + fail-closed bilinçli; doküman netleştirme |
| 6 | NPS duplicate policy | CONFIRM-BY-DESIGN | Wave 9'da 409 kapandı; `test_nps_duplicate_guard.py` 3/3 PASS |
| 7 | GraphQL introspection drift | OPERATOR-ENV | backend kod fail-closed doğru; stres backend env wiring eksik |
| 8 | Admin/settings RBAC surface | CONFIRM-BY-DESIGN | super_admin guard fail-closed 404 (Wave 8); stres admin tenant-scoped |

---

## 1. e-Fatura/e-Arşiv VKN-TCKN — SAFE-FIX (DONE)

**Kanıt:** `AccountingInvoiceCreateRequest.customer_tax_number`
(`backend/routers/finance/accounting.py`) format doğrulaması YOKTU — yalnız
insert'te `sanitize_plaintext(max_length=20)`. Paralel yol
`InvoiceCreate.customer_tax_id` (`backend/models/schemas/invoicing.py`) ise
10/11-haneli VKN/TCKN doğrulamasını uyguluyordu. Gerçek sözleşme tutarsızlığı:
bir e-fatura oluşturma yolu kimliği doğruluyor, diğeri çöp değer kabul ediyor →
GIB downstream malformed identifier üretebilir.

**Fix:** Ortak modül-seviye yardımcı `_normalize_customer_tax_number` eklendi
(strip → boş ise None → digit + len∈{10,11} değilse ValueError → 422).
`AccountingInvoiceCreateRequest.customer_tax_number` `field_validator`'ı bu
yardımcıyı çağırır; **ham-dict** alan `update_accounting_invoice` (post-create
malformed yazım kapısı) da aynı yardımcıyı çağırıp `ValueError`'ı 422'ye sarar →
create+update parite, tek doğruluk kaynağı. **Additive + geriye-uyumlu** (None/boş
kabul; yalnız çöp değer reddedilir). **Kapsam sınırı:** from-folio yolu
(`GenerateInvoiceFromFolioRequest`) `customer_tax_number` alanı KABUL ETMEZ ve şu
an set ETMEZ → o yola validator gereksiz; ayrıca türetilmiş/legacy veriyi
retroaktif 422'lememek için bilinçli dokunulmadı.

**Test:** `backend/tests/test_invoice_tax_id_contract.py` 13 yeni case
(model: optional/vkn/tckn/blank + 5 invalid; helper: none-blank + 2 valid + 5
invalid) → toplam 26/26 PASS.

**Kapanmayan (SCOPED-FOLLOW-UP):** `customer_type` zorunlu kılma + VKN↔TCKN
uzunluk-tipi tutarlılık zorlaması = geriye-uyum + migration gerektirir (Wave 9
deferred). Bu pakette zorlanmadı.

## 2. Revenue dry_run global kill-switch — SCOPED-FOLLOW-UP

**Kanıt:** Global env kill-switch (`REVENUE_DRY_RUN` vb.) YOK. Bunun yerine
tenant-seviye flag sistemi (`channel_manager/.../hotelrunner_v2/feature_flags.py`):
`shadow_mode` default **True** (mutation kill-switch ON), `write_enabled` default
**False**. Yani dış mutasyonlar zaten varsayılan-fail-safe. Core revenue router'lar
(`domains/revenue/.../rates.py`, `pricing_strategy.py`) doğrudan `db.rate_calendar`
yazıp gated ARI push tetikler.

**Karar:** Global env kill-switch çok-endpoint, prod write path'lerine dokunur,
mevcut tenant-flag güvenliğini tekrarlar → riskli/gereksiz. Scoped follow-up.
Operatör tam REVIEW metnini #168 artifact'tan (revenue_management REVIEW=1/SKIP=2)
çıkarıp gerçekten ihtiyaç netleşirse ayrı tur.

## 3. B2B per-subrouter scope provisioning — SCOPED-FOLLOW-UP

**Kanıt:** `agency_api_keys` modelinde scope/permission alanı YOK; tek agency key
13 alt-router'a erişiyor (paylaşımlı `get_b2b_agency` dependency). #168 spec 41B D
zaten "tasarım kararı; v3'te per-subrouter scope eklenirse P1 hard assert" diyor.

**Karar:** Per-subrouter scope = yeni ürün özelliği (key modeline scope alanı +
provisioning endpoint + 13 router'da enforcement + mevcut key'ler için migration).
Büyük + ürün-sözleşme kararı; "no broad RBAC grant" doktrini gereği zorlanmaz →
scoped follow-up, v3 tasarımı belgelenir.

## 4. CRM corporate contract approval lifecycle — CONFIRM + SCOPED

**Kanıt:**
- Agency contracts (`backend/routers/agency_contracts.py`): OLGUN state machine
  (pending→approved/rejected/terminated/withdrawn/expired) + `uniq_active_contract`
  partial-unique. Zaten tam.
- CRM companies (`domains/pms/misc/companies.py`): `status` pending/active/inactive
  — onay state machine değil, basit status.
- Corporate contracts (`domains/revenue/rms/...`): `status` draft/active/expired —
  formal approve/reject transition endpoint'i yok.

**Karar:** #168 module tablosunda crm_offers temiz (16/0/0/0); net açık REVIEW yok.
Agency tarafı by-design tam. Corporate-contract formal approval state machine
istenirse ayrı feature → scoped follow-up. Bu pakette kod değişmedi.

## 5. KVKK anonymize-only vs hard-delete — CONFIRM-BY-DESIGN

**Kanıt:** `POST /api/gdpr/guests/{guest_id}/anonymize`
(`backend/domains/admin/router/compliance.py`): PII alanlarını scrub eder
(full_name/email/phone/passport_number/id_number/birth_date/nationality/...),
finansal/audit bütünlüğü için kayıt iskeletini KORUR (`anonymized=True`,
`anonymized_at`, `anonymized_by`), `db.gdpr_requests`'e audit yazar, env
`ENABLE_GUEST_ANONYMIZATION` ile fail-closed (set değilse 503).

**Karar:** Anonymize-only + audit + fail-closed bilinçli KVKK/GDPR sözleşmesi;
hard-delete kasıtlı YOK (finansal kayıt bütünlüğü). #168 kvkk SKIP/REVIEW'ları bu
by-design davranışın yansıması. Kod değişmez; sözleşme bu dokümanda netleştirildi.

## 6. NPS duplicate policy — CONFIRM-BY-DESIGN (Wave 9 closed)

**Kanıt:** `submit_survey_response`
(`backend/domains/guest/experience_router/feedback.py`): booking_id verildiğinde
(survey, booking) UTC-gün başına tek yanıt → 409. `booking_id`'siz ad-hoc muaf.
`backend/tests/test_nps_duplicate_guard.py` **3/3 PASS** (bu turda doğrulandı).

**Karar:** Backend sözleşmesi Wave 9'da kapandı ve testli. #168 public_nps REVIEW=1
stres-spec gözlemi (CI-deferred, canlı stres backend gerektirir); kod gap değil.

## 7. GraphQL introspection drift — OPERATOR-ENV

**Kanıt:** `_introspection_enabled()` (`backend/graphql_api/schema.py:499`):
`GRAPHQL_INTROSPECTION` açıkça true/1 → açık (lokal opt-in); aksi halde env
(`SENTRY_ENVIRONMENT`|`APP_ENV`|`ENVIRONMENT`) ∈ {production,prod,stress,staging}
→ KAPALI; diğer (dev) → açık. **Backend kod fail-closed DOĞRU.**

**Kök sebep:** #168 introspection ON (types=25) — çünkü stres BACKEND deployment'ı
yukarıdaki env sinyallerinden hiçbirini "stress" set etmiyor (dev'e düşüyor) ya da
`GRAPHQL_INTROSPECTION=true`. Bu Package A+B'deki KBS/HotelRunner gibi
operatör-kontrollü backend-env wiring; kod görevi YOK.

**Operatör aksiyonu:** stres backend deployment env'inde `SENTRY_ENVIRONMENT=stress`
(veya APP_ENV/ENVIRONMENT) set → introspection otomatik kapanır; alternatif
`GRAPHQL_INTROSPECTION=false`. Prod aynı şekilde. (digitalocean.md env listesi zaten her
iki değişkeni içeriyor — yeni env eklenmedi.)

## 8. Admin/settings RBAC surface — CONFIRM-BY-DESIGN (Wave 8)

**Kanıt:** `require_super_admin_guard(not_found=True)` (`backend/core/helpers.py:252`):
super_admin olmayana 403 değil **404** (varlık gizleme). `/api/admin/tenants`,
`/api/admin/feature-flags`, `/api/webhooks/status`, `/api/outbox/status` bununla
korunuyor. Stres ADMIN token bilinçli tenant-scoped, platform super_admin DEĞİL →
404 DOĞRU fail-closed davranış.

**Karar:** #168 admin_rbac/settings_audit/hr_rbac_pii "endpoint_not_deployed"
spec etiketi misclassification (gerçek: super_admin-guard-fail-closed-404). Wave 8
bunu zaten belgeledi; 2xx yapmak = auth weakening = YASAK. Kod değişmez.

---

## Sonuç

- **Tek kod değişikliği:** Target 1 e-Fatura `customer_tax_number` parite
  validator (additive, geriye-uyumlu) + 9 yeni targeted test (18/18 PASS).
- **Operatör-env:** Target 7 GraphQL (stres backend env wiring).
- **By-design (kod yok):** Target 5 KVKK, 6 NPS, 8 Admin-RBAC, 4 agency-contract.
- **Scoped follow-up:** Target 2 revenue global kill-switch, 3 B2B scope,
  4 corporate-contract approval, 1 customer_type-zorunlu.
- external_calls=[], pilot mutation yok, RBAC grant yok, auth weakening yok.
- Baseline #168 pointer TAŞINMAZ; targeted regression PASS; full stress CI-deferred.
