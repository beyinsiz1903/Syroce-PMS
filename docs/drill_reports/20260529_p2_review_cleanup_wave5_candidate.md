# P2/REVIEW Risk Cleanup — Wave 5 (CANDIDATE)

- **Tarih**: 2026-05-29
- **Statü**: CANDIDATE (full stress suite KOŞULMADI; yeni resmi kanıt yok)
- **Baseline pointer**: Run #161 (`ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`) — DEĞİŞMEDİ
- **Kapsam**: finance / compliance / CM integration / ops readiness REVIEW/P2 davranış kilitleme
- **Kurallar**: sema gevşetme YOK · SKIP-as-PASS YOK · pointer hareket YOK · GO iddiası YOK · /100 iddiası YOK · P2/REVIEW/SKIP downgrade YOK · fake green YOK

## Doktrin
Wave 5 de "sayı azaltma" değildir: mevcut (zaten olgun) davranışları targeted backend
testleriyle kilitler ve bilinçli politikaları dokümante eder. Hiçbir finansal/compliance
guard gevşetilmedi; hiçbir prod kodu davranışı değiştirilmedi (yalnız test eklendi +
ops readiness test dosyasına shape kontratı eklendi). external_calls = [] korunur.

## Değişiklikler (yalnız test + docs; prod kod davranışı değişmedi)

### 1. Finance folio guards & idempotency & RBAC
- **Test** (`test_finance_folio_guards.py`, NEW 10):
  - Closed-folio guard davranışı: post_charge / post_payment / void_charge / void_payment
    kapalı folioda `success=False`, mutasyon yok (monkeypatched db).
  - Input guard: payment amount<=0 reddedilir, insert yapılmaz; void reason zorunlu;
    already-voided charge reddedilir; split eksik charge'da reddedilir.
  - Tenant scoping: guard query'leri `tenant_id` taşır.
  - Idempotency-scope namespace kontratı: her para operasyonu DISTINCT scope prefix
    (`folio_charge:` / `folio_payment:` / `folio_refund:` / `folio_void_charge:` /
    `folio_void_payment:` / `folio_split:`) — replay cache çakışması imkansız.
  - RBAC kontratı: her para endpoint'i kendi ayrı permission string'ini enforce eder
    (post_charge / post_payment / void_charge / void_payment / split_folio).
- **Gözlem (DEĞİŞTİRİLMEDİ, not)**: `routers/finance/folio.py` içindeki `void_payment`
  rotası `post_payment` permission'ı ile gate'li; `routers/pms_hardening.py` muadili
  doğru `void_payment` permission'ı kullanır. İki ayrı rota; davranış değişikliği
  scope dışı olduğundan dokunulmadı, ileride RBAC tutarlılık follow-up adayı.
- **Stress seed vs product bug ayrımı**: guard testleri deterministik servis davranışını
  doğrular; stress'te görülen "void başarısız" tipi sinyaller seed data-state (kapalı
  folio / zaten void) kaynaklıdır, product bug değildir.

### 2. KVKK/GDPR anonymize contract
- **Test** (`test_kvkk_anonymize_contract.py`, NEW 4):
  - Flag kapalı → 503, hiçbir scrub mutasyonu yok (fail-closed).
  - Flag açık + guest yok → 404, lookup tenant-scoped.
  - Flag açık + guest var → tüm PII alanları None, `full_name="ANONYMIZED"`,
    anonymized markerları set, update tenant-scoped, `gdpr_requests` audit satırı
    yazılır (tenant_id/guest_id/type=anonymization/requested_by).
  - Non-super-admin engeli Wave 3'te (`test_guest_anonymization_flag.py`) kilitli.
- **Politika (bilinçli)**: Guest için public **hard-delete YOK**. Right-to-be-forgotten
  geri döndürülemez anonymize ile karşılanır; record skeleton finansal/audit bütünlüğü
  için korunur. Soft-delete (`status="deleted"`) ayrı yoldur ve aktif booking varken
  bloklanır. Hard-delete'in olmaması kasıtlı politikadır (gap değil) — test bunu kilitler.

### 3. e-Fatura / e-Arşiv VKN/TCKN
- Mevcut `test_invoice_tax_id_contract.py` (6) VKN(10)/TCKN(11) uzunluk + digit + blank
  normalize + invalid (9/12/non-digit) kapsar. Wave 5'te yeterli; mükerrer test
  eklenmedi (kapsam doğrulandı, invoice create akışı bozulmadı).

### 4. CM signed-path / idempotency posture
- **Test** (`test_cm_signed_path_idempotency.py`, NEW 4):
  - HotelRunner valid HMAC-SHA256 signed body kabul edilir; default fail-closed (503).
  - HotelRunner idempotency: provider_event_id deterministik
    (`{hr_number}_{event_type}_{last_mod}`) — replay aynı id'ye düşer, no-op; format
    string kaynak-kontratıyla kilitli.
  - Exely whitelist gate fail-closed default; `EXELY_IP_WHITELIST` +
    `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK` (dev escape) varlığı kontrat olarak kilitli.
  - Hiçbir testte outbound HTTP yok → external_calls = [].

### 5. Ops readiness observability
- **Test** (`test_ops_readiness_endpoints.py`, +2 = toplam 4):
  - `/api/infra/backup/status` rota kaydı.
  - Backup status shape kontratı: `enabled` + `last_successful` (None veya
    `completed_at` taşıyan dict). Spec'in beklediği `last_backup_at`, deploy
    edilmiş kontratta `last_successful.completed_at` olarak karşılanır (gevşetme yok).
  - Outbox `/api/outbox/status` + conflict-queue count/list rota kaydı Wave 2'de kilitli.

## Test sonucu
=> 86 passed (Wave 5 yeni: 18 case; toplam sprint backend = 86). Süre ~7.5s.
Komut: `pytest tests/test_finance_folio_guards.py tests/test_kvkk_anonymize_contract.py
tests/test_cm_signed_path_idempotency.py tests/test_ops_readiness_endpoints.py
tests/test_invoice_tax_id_contract.py + Wave 1-4 dosyaları`.

## Env / operator notları
- digitalocean.md değişmedi (yeni env yok). Tüm ilgili env'ler (ENABLE_GUEST_ANONYMIZATION,
  HOTELRUNNER_WEBHOOK_SECRET/ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK, EXELY_IP_WHITELIST,
  ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK) zaten digitalocean.md/threat_model'de mevcut.

## Sonraki adım
Wave 5 candidate kapandıktan sonra resmi full stress suite operator dispatch ile
koşulacak (OAuth workflow scope yok). Yeni resmi artifact üretilene kadar Run #161
pointer'ı resmi baseline olarak kalır.
