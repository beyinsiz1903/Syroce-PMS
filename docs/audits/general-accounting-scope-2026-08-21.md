# Genel Muhasebe Kapsam Denetimi — 2026-08-21

## Sonuç ve 2026-08-22 iyileştirme durumu

Sistem artık çift taraflı kayıt, dönem kilidi, bağlı ters kayıt, tekrar güvenli
posting, minor-unit para aritmetiği, bilanço ve gelir tablosu ile kapanış kontrollü
bir **GL çekirdeği** sunuyor. AP faturası/ödemesi, sabit kıymet amortismanı,
PMS/POS ve Nilvera belgeleri otel bazlı, opt-in hesap eşlemeleriyle aynı çekirdeğe
bağlıdır. Kur değerleme, karşılaştırmalı rapor, zincir eliminasyonu ve doğrulanmış
e-Defter kaynak paketi hazırdır. Resmî XBRL-GL/berat, mali mühür ve GİB gönderimi
haricî uyumluluk/onay sınırında kalır.

## Mevcut ve doğrulanan kapsam

| Alan | Durum | Kanıt |
| --- | --- | --- |
| Tek Düzen hesap planı | Var | `backend/domains/accounting/gl_router.py` — hesap listeleme, oluşturma, ilk kurulum ve güncelleme |
| Çift taraflı yevmiye | Var | `shared_kernel/gl_posting.py`, `/api/gl/journal` |
| Mizan | Var | `/api/gl/trial-balance` ve `GeneralLedgerModule.jsx` |
| Nilvera alış/satış faturası → GL | Hazır | Otel bazlı eşleme, review/automatic kuyruk, vergi/tevkifat, alış dövizi, satış iptal ters kaydı |
| Mali dönem ve kilit | Hazır | PR #360; sıralı kapatma, kontrollü yeniden açma ve audit |
| Bağlı ters kayıt | Hazır | PR #361; özgün fiş değişmeden karşı fiş üretimi |
| Satıcı faturaları / ödemeler / yaşlandırma | GL bağlantısı hazır | Opt-in hesap eşlemesi, idempotent fatura/ödeme fişi, void ters kaydı ve retry |
| Bütçe / gerçekleşen karşılaştırması | Backend + çalışma alanı özeti hazır | `backend/domains/accounting/budget_router.py`, `GeneralLedgerModule.jsx` |
| Sabit kıymet / amortisman | GL bağlantısı hazır | Kıymet/dönem bazlı idempotent amortisman fişi ve hata sonrası retry |
| Gelir tablosu / bilanço | Hazır | `/api/gl/statements/*`, minor-unit hesaplama ve Genel Muhasebe ekranı |
| Bordro → GL | Backend var | `backend/domains/accounting/payroll_gl_router.py`; İK ekranından tetikleniyor |
| Banka mutabakatı | Ayrı ekran var | `/app/bank-reconciliation` |

## Eksikler ve öncelik

### Tamamlanan P0 — Muhasebe bütünlüğü / kapanış güvenliği

1. Dönem modeli, sıralı kapatma, ters sırada yeniden açma ve audit eklendi.
2. Özgün fişe bağlı, değiştirilemez ve idempotent ters kayıt eklendi.
3. Manuel posting idempotency anahtarı zorunlu ve içerik parmak iziyle korumalı.
4. GL parasal doğruluk kaynağı `debit_minor` / `credit_minor`; API uyumluluğu için
   eski ondalık görünüm türetilmiş çıktı olarak korunuyor.

### Tamamlanan P1 çekirdeği — Ürün kapsamı / erişilebilirlik

1. AP yaşlandırma, aylık gelir/gider bütçe karşılaştırması ve sabit kıymet özeti
   Genel Muhasebe içindeki `Alt Defterler` sekmesine bağlandı.
2. Yılbaşından bugüne gelir tablosu ve tarih itibarıyla bilanço endpoint/UI'ı eklendi.
3. Gerçek `finance` rolünün AP/bütçe/sabit kıymet erişimi düzeltildi; ilgili sekiz
   koleksiyon sıkı tenant kapsamına alındı.

Kalan ürün deneyimi işi: yevmiye detay/filtre/dışa aktarma ve hesap planı
oluşturma-güncelleme formlarının arayüze taşınmasıdır. Bunlar veri bütünlüğü
engeli değil, kullanım kolaylığı kapsamıdır.

### P2 — Mevzuat ve operasyon olgunluğu

1. Resmî XBRL-GL dosyaları, berat, mali mühür/e-imza ve GİB gönderimi yok; mevcut
   çıktı yalnızca bütünlük manifestli mali müşavir/uyumlu yazılım kaynak paketidir.
2. Genel fiş hazırlayan-onaylayan ayrılığı ve taslak/onay/posting yaşam döngüsü yok.
3. Nilvera dışındaki yabancı para alt defterlerinde kur kaynağı/eşlemesi ürün
   bazında ayrıca tanımlanmalıdır; GL satırları işlem para birimini korur.

## Kalan teslim sırası

1. Hazırlayan-onaylayan ayrılığı ve fiş taslak/onay/posting yaşam döngüsü.
2. Mali müşavir doğrulaması, uyumlu yazılım/onay, mali mühür ve resmî e-Defter
   berat entegrasyonu.

Bu denetim yalnızca kod ve route kapsamını değerlendirir; provider write veya
production işlemi yapılmamıştır.
