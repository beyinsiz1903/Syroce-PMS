# Genel Muhasebe Kapsam Denetimi — 2026-08-21

## Sonuç

Mevcut sistem, çift taraflı kayıt çekirdeği ve bazı alt defter köprüleri sayesinde
işlevsel bir **GL temeli** sunuyor; ancak bugün itibarıyla uçtan uca, kapanış
kontrollü bir genel muhasebe ürünü sayılmamalı. Otel kullanıcısına açılan
`Genel Muhasebe` ekranı backend kapsamının yalnızca küçük bir bölümünü gösteriyor.

## Mevcut ve doğrulanan kapsam

| Alan | Durum | Kanıt |
| --- | --- | --- |
| Tek Düzen hesap planı | Var | `backend/domains/accounting/gl_router.py` — hesap listeleme, oluşturma, ilk kurulum ve güncelleme |
| Çift taraflı yevmiye | Var | `shared_kernel/gl_posting.py`, `/api/gl/journal` |
| Mizan | Var | `/api/gl/trial-balance` ve `GeneralLedgerModule.jsx` |
| Nilvera alış/satış faturası → GL | Var | `backend/core/integrations/invoice_gl_bridge.py`, GL entegrasyon uçları |
| Satıcı faturaları / ödemeler / yaşlandırma | Backend var | `backend/domains/accounting/ap_router.py` |
| Bütçe / gerçekleşen karşılaştırması | Backend var | `backend/domains/accounting/budget_router.py` |
| Sabit kıymet / amortisman | Backend var | `backend/domains/accounting/fixed_asset_router.py` |
| Bordro → GL | Backend var | `backend/domains/accounting/payroll_gl_router.py`; İK ekranından tetikleniyor |
| Banka mutabakatı | Ayrı ekran var | `/app/bank-reconciliation` |

## Eksikler ve öncelik

### P0 — Muhasebe bütünlüğü / kapanış güvenliği

1. **Dönem yönetimi ve dönem kilidi yok.** Açık/kapalı mali dönem modeli,
   kapanmış döneme kayıt engeli ve kontrollü yeniden açma/audit akışı bulunmuyor.
2. **Standart ters kayıt/iptal fişi akışı yok.** Yevmiye için kullanıcıya açık,
   özgün kayda bağlı ve denetlenebilir reversal endpoint/UI sözleşmesi bulunmuyor.
3. **Manuel fişte idempotency zorunlu değil.** Backend anahtar kabul ediyor fakat
   `GeneralLedgerModule.jsx` manuel kayıtta anahtar göndermiyor; ağ tekrarları çift
   kayıt riski yaratabilir.
4. **Parasal alanlar float.** GL giriş modellerinde `float` kullanımı kuruş ve
   yuvarlama tutarlılığı açısından finansal kayıt için yeterli güvence vermiyor;
   Decimal/minor-unit standardı gerekli.

### P1 — Ürün kapsamı / erişilebilirlik

1. **Backend alt modülleri Genel Muhasebe ekranında yok.** AP, bütçe, sabit kıymet
   ve amortisman uçları mevcut olmasına rağmen tek kullanıcı çalışma alanında
   menü/sekmelerle erişilemiyor.
2. **Temel mali tablolar yok.** Bilanço ve gelir tablosu endpoint/UI çıktısı yok;
   yalnızca mizan mevcut.
3. **Yevmiye detay ve filtre deneyimi eksik.** Backend tarih filtresi ve detay ucu
   sağlıyor; UI bunları tam kullanmıyor, dışa aktarma da sunmuyor.
4. **Hesap planı yönetimi eksik.** Backend hesap oluşturma/güncelleme sunuyor;
   UI sadece ilk kurulum ve listeleme yapıyor.

### P2 — Mevzuat ve operasyon olgunluğu

1. Büyük defter/yevmiye defteri resmi çıktıları ve berat/e-Defter süreci yok.
2. Kur farkı, yeniden değerleme, tahakkuk/gelecek aylara ait gider ve otomatik
   kapanış fişleri yok.
3. Çoklu para birimli GL kayıt politikası ve fonksiyonel/işlem para birimi
   bakiyeleri görünür değil.
4. Onay matrisi (hazırlayan/onaylayan) ve fiş taslak-onay-posting yaşam döngüsü yok.

## Önerilen teslim sırası

1. P0: mali dönem kilidi + reversal + zorunlu idempotency + Decimal para modeli.
2. P1: mevcut AP/bütçe/sabit kıymet yeteneklerini tek Muhasebe çalışma alanına
   bağlama; bilanço ve gelir tablosu.
3. P2: e-Defter/resmi çıktılar, dövizli muhasebe ve onay iş akışı.

Bu denetim yalnızca kod ve route kapsamını değerlendirir; provider write veya
production işlemi yapılmamıştır.
