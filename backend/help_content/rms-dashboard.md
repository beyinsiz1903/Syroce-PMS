# RMS Dashboard — Talep, Esneklik, Tahmin

**Revenue Management System (RMS)**, AI/ML algoritmalarıyla talep tahmini, fiyat esnekliği analizi, rezervasyon olasılığı ve iptal riski hesaplayan modüldür.

## Dashboard'taki 4 Pipeline

1. **Talep Tahmini (Demand Forecast)** — gelecek 7/14/30/60/90 günlük doluluk projeksiyonu
2. **Fiyat Esnekliği (Price Elasticity)** — fiyat değişiminin rezervasyon hacmine etkisi
3. **Rezervasyon Olasılığı (Booking Probability)** — açık rezervasyon talebinin gerçekleşme şansı
4. **İptal Riski (Cancellation Risk)** — onaylı rezervasyonun iptal olma olasılığı

Tüm pipeline'lar **paralel** (`asyncio.gather`) çalışır; biri hata verirse diğerleri görüntülenmeye devam eder (kısmî sonuç + hata uyarısı).

## Dinamik Fiyatlandırma

RMS önerilerine göre sistem:

- Yarın için doluluk %85'i geçerse **fiyatı %10 artır** önerir
- Önümüzdeki hafta sonu için talep zayıfsa **flash kampanya** önerir
- AI önerileri **otomatik uygulanmaz**; revenue manager onayıyla [Channel Manager](#/help/channel-manager) üzerinden tüm kanallara push edilir

## Upsell Önerileri

Check-in sırasında AI, misafir profiline göre upsell teklifleri (oda yükseltme, geç çıkış paketi, spa kombosu) sunar; resepsiyonist tek tıkla folio'ya ekler.

## No-Show Risk

Yarın gelecek rezervasyonlar **risk skoru** ile sıralanır:

- Yüksek risk → resepsiyon proaktif arar
- Çok yüksek risk → otomatik garantili kart onayı talep edilir

## Misafir Pattern Analizi

Tekrar gelen misafirlerin tercihleri (oda tipi, kat, özel istekler) öğrenilir; sonraki rezervasyonda otomatik uygulanır.

## Sağlık & Hata Durumu

Sağ üstte **Yenile** butonu mevcut. Bir pipeline 45 saniyeden uzun sürerse zaman aşımı uyarısı verilir, diğer paneller çalışmaya devam eder. Yetki yetersizse 403 mesajı net Türkçe gösterilir.

## Yapılandırma

**Yönetim > Ayarlar > AI / RMS** ekranından:

- Pipeline'ların açık/kapalı durumu
- Tahmin ufkunu (gün)
- Otomatik fiyat önerisi minimum/maksimum % sınırı
