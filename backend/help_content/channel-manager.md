# Channel Manager — Exely & HotelRunner

Online satış kanallarınızla (Booking.com, Expedia, Airbnb, Agoda, Hotels.com, Trip.com vb.) **iki yönlü senkronizasyon**: PMS'den kanallara müsaitlik/fiyat gönderme, kanallardan PMS'ye rezervasyon çekme.

## Desteklenen Sağlayıcılar

- **Exely** — kapsamlı OTA bağlantısı, webhook tabanlı rezervasyon push
- **HotelRunner** — periyodik (3 dakikada bir) pull tabanlı senkron
- **Sabre SynXis (HTNG 2024B)**, **SAP S/4HANA (OData V4)** — kurumsal entegrasyon

## Unified Rate Manager

**Kanallar > Rate Manager** ekranı tek bir grid'de tüm kanalların:

- Fiyatları (oda tipi × tarih)
- Kontenjanı (allotment)
- Restriksiyonları (CTA / CTD / MinLOS / MaxLOS / Stop Sell)

görünümünü sunar. Hücre üzerinde değişiklik yapıldığında **tüm bağlı kanallara** push edilir.

## Senkronizasyon Sıklığı

| Kanal | Yön | Sıklık | Notlar |
|-------|-----|--------|--------|
| Exely | Push (rezervasyon) | Webhook anlık | IP whitelist zorunlu (üretimde `EXELY_IP_WHITELIST` set olmalı) |
| Exely | Pull (fiyat/availability) | Scheduler | Manuel "Şimdi Senkronize Et" mevcut |
| HotelRunner | Pull | 3 dk | Otomatik retry (transient 504'leri yutar — ortalama +6sn gecikme) |
| HotelRunner | Push | Manuel + scheduler | Çakışmada PMS kazanır |

## SXI (Syroce Xchange)

Tüm kanal olayları **SXI bus** üzerinden iç servislere yayınlanır:

- **Idempotent** — aynı olay iki kez işlenmez
- **SSRF korumalı** — outbound URL'ler IP allowlist + transport pinning ile filtrelenir
- **Retry + DLQ** — 5 başarısız denemeden sonra dead-letter kuyruğuna düşer; manuel müdahale ile tekrar denenebilir

## Çakışma & Çift Rezervasyon

İki kanaldan aynı oda için aynı tarihe rezervasyon gelirse:

- **MongoDB unique compound index** atomik olarak ikinciyi reddeder
- Reddedilen rezervasyon **"Çakışan Rezervasyon"** raporuna düşer
- Operatör manuel oda değişimi veya iptal kararı verir

## Sağlık İzleme

**Altyapı > Kanallar Hub > Sağlık** ekranı her bağlantı için son senkron zamanı, hata oranı, ortalama gecikme gösterir. Kırmızıya dönen kanallar için yöneticiye e-posta + push bildirim gider.

## Sık Hatalar

- **Exely 503**: üretimde IP whitelist boş → `EXELY_IP_WHITELIST` ortam değişkeni doldurulmalı
- **HotelRunner 504**: gateway timeout — otomatik retry devreye girer; iki turdan sonra hâlâ hata varsa kanal "Degraded" işaretlenir
- **Rate Manager push reddedildi**: kanal tarafında Stop Sell aktif olabilir; kanal panelinden kaldırılır
