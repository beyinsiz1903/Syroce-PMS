# Genel Muhasebe Kapsam Denetimi — 2026-08-21

## Sonuç ve 2026-08-22 iyileştirme durumu

Sistem artık çift taraflı kayıt, dönem kilidi, bağlı ters kayıt, tekrar güvenli
posting, minor-unit para aritmetiği, bilanço ve gelir tablosu ile kapanış kontrollü
bir **GL çekirdeği** sunuyor. AP, bütçe ve sabit kıymet özetleri de aynı Genel
Muhasebe çalışma alanından erişilebilir. Bu çekirdek operasyonel muhasebe için
işlevseldir; e-Defter/berat, döviz değerleme ve hazırlayan-onaylayan yaşam döngüsü
tamamlanmadan mevzuat uçtan uca tamamlandı kabul edilmemelidir.

## Mevcut ve doğrulanan kapsam

| Alan | Durum | Kanıt |
| --- | --- | --- |
| Tek Düzen hesap planı | Var | `backend/domains/accounting/gl_router.py` — hesap listeleme, oluşturma, ilk kurulum ve güncelleme |
| Çift taraflı yevmiye | Var | `shared_kernel/gl_posting.py`, `/api/gl/journal` |
| Mizan | Var | `/api/gl/trial-balance` ve `GeneralLedgerModule.jsx` |
| Nilvera alış/satış faturası → GL | Var | `backend/core/integrations/invoice_gl_bridge.py`, GL entegrasyon uçları |
| Mali dönem ve kilit | Hazır | PR #360; sıralı kapatma, kontrollü yeniden açma ve audit |
| Bağlı ters kayıt | Hazır | PR #361; özgün fiş değişmeden karşı fiş üretimi |
| Satıcı faturaları / ödemeler / yaşlandırma | Backend + çalışma alanı özeti hazır | `backend/domains/accounting/ap_router.py`, `GeneralLedgerModule.jsx` |
| Bütçe / gerçekleşen karşılaştırması | Backend + çalışma alanı özeti hazır | `backend/domains/accounting/budget_router.py`, `GeneralLedgerModule.jsx` |
| Sabit kıymet / amortisman | Backend + çalışma alanı özeti hazır | `backend/domains/accounting/fixed_asset_router.py`, `GeneralLedgerModule.jsx` |
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

1. Büyük defter/yevmiye defteri resmi çıktıları ve berat/e-Defter süreci yok.
2. Kur farkı, yeniden değerleme, tahakkuk/gelecek aylara ait gider ve otomatik
   kapanış fişleri yok.
3. Çoklu para birimli GL kayıt politikası ve fonksiyonel/işlem para birimi
   bakiyeleri görünür değil.
4. Onay matrisi (hazırlayan/onaylayan) ve fiş taslak-onay-posting yaşam döngüsü yok.

## Kalan teslim sırası

1. Yevmiye filtre/detay/dışa aktarma ve hesap planı yönetim ekranları.
2. Hazırlayan-onaylayan ayrılığı ve fiş taslak/onay/posting yaşam döngüsü.
3. Çoklu para birimi, kur farkı, tahakkuk ve otomatik kapanış fişleri.
4. Mali müşavir ve mevzuat doğrulamasıyla e-Defter/resmi çıktı paketi.

Bu denetim yalnızca kod ve route kapsamını değerlendirir; provider write veya
production işlemi yapılmamıştır.
