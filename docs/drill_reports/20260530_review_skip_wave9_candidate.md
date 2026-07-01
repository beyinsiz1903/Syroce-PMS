# REVIEW/SKIP Zeroing — Wave 9 candidate (2026-05-30)

> RBAC / PII / Product-Contract karar turu. Baseline **Run #162 pointer DEĞİŞMEDİ**
> (commit `bde7662744c9b94a5c9294fa778202d813319dfc`). Full stress suite bu turda
> KOŞTURULMADI — yalnız targeted backend testleri. Doktrin: fake-green YOK, kör stub
> YOK, geniş RBAC grant YOK, PII açığa çıkarma YOK, auth zayıflatma YOK, pilot mutation
> YOK, `external_calls=[]`. "GO" / "/100" iddiası YOK.

## Kapsam

Wave 9 hedefi 8 yüzey: bunlar teknik gap değil, ürün/RBAC sözleşme kararı. Her biri
dürüstçe incelendi, sınıflandırıldı; yalnız minimal güvenli düzeltmeler (RBAC sıkılaştırma
/ validation / 409 dup-guard) targeted testlerle uygulandı, gerisi by-design teyit ya da
gerekçeli scoped follow-up'a ertelendi.

## DONE — uygulanan minimal güvenli düzeltmeler (targeted test PASS)

### FIX #1 — Messaging activity PII mask (güvenlik sıkılaştırma)
- **Sorun**: `routers/messaging.py` `/activity` feed, recipient (guest e-posta/telefon) ham
  değerini serbest-metin `message` alanına gömüyordu ve yalnız `get_current_user` ile
  korunuyordu. Kardeş `/delivery-logs` rotası `view_guest_list` (VIEW_REPORTS) istiyor →
  tutarsızlık + düşük-yetkili rollere PII sızıntısı.
- **Düzeltme**: `_mask_recipient()` helper + `RolePermissionService` import; caller
  `view_guest_list` taşımıyorsa recipient maskelenir (privileged ham görür; admin/super_admin
  her op'u geçer). Tenant scoping korunur.
- **Test**: `test_messaging_activity_pii_rbac.py` — privileged vs non-privileged davranış +
  tenant-scoped query assert.

### FIX #8 — Finance folio `void_payment` RBAC mismatch (sıkılaştırma)
- **Sorun**: `routers/finance/folio.py::void_payment` rotası `post_payment` (POST_PAYMENT)
  permission'ı ile gate'liydi; `pms_hardening.py` muadili doğru `void_payment` (VOID_CHARGE)
  kullanıyor. FRONT_DESK'te POST_PAYMENT var ama VOID_CHARGE yok → istenmeyen void yetkisi.
- **Düzeltme**: enforce `post_payment` → `void_payment`. FINANCE/ADMIN'de VOID_CHARGE var,
  meşru erişim kaybı yok; FRONT_DESK'in yanlış void yetkisi kalkar (tightening).
- **Test**: `test_folio_void_payment_rbac.py` — davranış + source-contract (re-loosening guard).

### FIX #3 — CRM kurumsal `tax_number` tenant-içi tekillik (ürün sözleşmesi)
- **Karar**: kurumsal hesabın vergi numarası tenant içinde tekildir (Murat kararı).
- **Düzeltme**: `domains/pms/misc/companies.py` create_company + update_company — değer
  verildiğinde tenant-scoped dup → **409**. Yalnız değer varken uygulanır (alan opsiyonel,
  geriye-uyumlu); whitespace normalize edilir ve boş/whitespace-only **None** olarak saklanır
  (kirli değer persist edilmez). Update self-exclusion (`id $ne`). Tek insert path doğrulandı
  (başka `db.companies.insert_one` yok).
- **Test**: `test_company_tax_no_unique.py` — create dup 409, unique geçer, tax_no'suz guard
  atlanır, whitespace-only None persist (create+update), update başka-kayıt dup 409.

### FIX #7 — NPS / survey response gün-başına-tek (ürün sözleşmesi)
- **Karar**: aynı (survey, booking) için UTC gün başına tek yanıt (Murat kararı) —
  ballot-stuffing / yinelenen NPS kaydını engeller.
- **Düzeltme**: `domains/guest/experience_router/feedback.py::submit_survey_response` —
  booking_id varsa tenant + survey + booking + UTC gün-aralığı dup → **409**. booking_id'siz
  ad-hoc yanıt muaf (eşleştirilemez). Aralık sorgusu ISO-string `submitted_at` (isoformat) ile
  lexical tutarlı, index-dostu.
- **Test**: `test_nps_duplicate_guard.py` — aynı-gün dup 409, ilk yanıt geçer, booking_id'siz
  guard atlanır.

**Targeted test toplamı: 21 passed** (4 dosya). `node`/import sanity temiz.

## CONFIRM — by-design (kod değişmedi)

- **#2 GraphQL introspection**: `test_graphql_introspection_policy.py` (7) zaten prod/stress
  default-off + explicit opt-in + normal query çalışır. Rule yalnız `__schema`/`__type`
  meta-field kaldırır, tenant-scoped resolver'lara dokunmaz. **By-design, değişiklik yok.**
- **#6 KVKK anonymize / hard-delete**: anonymize + `gdpr_requests` audit + fail-closed (flag
  kapalı→503) zaten var (`test_kvkk_anonymize_contract.py`, 4). Public hard-delete YOK kasıtlı
  (geri-dönülemez anonymize + record skeleton finansal/audit için korunur; soft-delete ayrı yol).
  **By-design, değişiklik yok.**

## DEFER — gerekçeli scoped follow-up tur (bu turda uygulanmadı)

Her ikisi de bu oturumda full-stress ile doğrulanamaz ve daha geniş/riskli değişiklik ister;
Wave 6/8 "ayrı tur" emsaliyle tutarlı ertelenir (sessiz drop DEĞİL — karar kayıtlı).

- **#4 e-Fatura/e-Arşiv VKN/TCKN identity schema**: mevcut şema VKN/TCKN'yi *opsiyonel*
  tutuyor (eski çağıranlar kırılmasın diye); `customer_type`'a göre **zorunlu** kılmak
  geriye-uyumu bozar + discriminator + migration ister. Mevcut kontrat testi
  `test_invoice_tax_id_contract.py` (6) korunur. Scoped follow-up: `customer_type` ayrımı +
  type-conditional zorunluluk + migration değerlendirmesi.
- **#5 Revenue auto-publish `dry_run` kill-switch**: server-side mutation-suppression gate'i
  birden çok apply endpoint'ine dokunan feature eklentisidir; targeted-only doğrulanamaz.
  Scoped follow-up: tüm publish/apply yollarında `dry_run` honor + RBAC.

## RECLASSIFY — RBAC by-design (alt-role veya out-of-scope)

`mice_events`, `mice_opportunities`, `accommodation_tax`, `vcc_pci_compliance`, `public_kvkk`,
`hr_shift` (swap consent) — hepsi RBAC by-design (sales-catering / tax_officer /
cashier_supervisor rolü yok ya da consent self-grant engeli). Karar: alt-role spec VEYA
out-of-scope kabul. Kod değişikliği yok.

## AÇIK KARAR (Murat'a)

- **#3b CRM contract approval lifecycle**: ürün kararı açık — ayrı tur / karar bekliyor.
- **inventory_transfer_procurement** (E9/E10 warehouse-transfer + supplier credit_limit):
  feature implemente değil → program-dışı backend backlog.

## Hardening önerisi (opsiyonel, bu turda uygulanmadı)

- `companies` için `(tenant_id, tax_number)` partial/sparse unique index → 409 dup-guard'ı
  race-safe yapar. Mevcut veride olası duplicate'ler için migration ister; full validation
  olmadan eklenmedi.

## Doktrin teyidi

Baseline #162 pointer TAŞINMADI. Full stress KOŞTURULMADI (targeted-only). Fake-green YOK,
kör stub YOK, geniş RBAC grant YOK (yalnız sıkılaştırma + dup-guard), PII açığa çıkarma YOK
(maskeleme eklendi), auth zayıflatma YOK, pilot mutation YOK, `external_calls=[]`. Targeted
spec PASS CI-deferred. Architect: PASS (whitespace-normalize caveat uygulandı + regresyon
testi eklendi).
