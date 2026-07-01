# Dinamik Fiyat, Tahmin ve Öneriler

Gelir yönetimi (RMS), doluluk ve talebe göre fiyat önerileri üretir. Öneriler karar desteğidir; onay insandadır.

## Talep tahmini

- Sistem geçmiş veriyle doluluk/talep tahmini üretir.
- Tahmin edilen doluluk **yüzde (0-100)** olarak tutulur; hesaplamada bu dikkate alınır.
- Veri yetersizse sistem değer uydurmaz; fail-closed davranır.

## Fiyat önerileri

- RMS, oda tipi ve tarih için önerilen fiyatı sunar.
- Öneri tablosunda mevcut fiyat, önerilen fiyat ve gerekçe görünür.
- Öneriler **onaylanmadan** kanallara gitmez.

## Revenue Autopilot

- Otomatik mod yalnızca yerel fiyat planlarını günceller (kanal push'u ayrıdır).
- Eşleşen plan yoksa "uygulandı" işareti konmaz; öneri beklemede kalır.

> Öneriyi körlemesine uygulamak yerine gerekçesini değerlendirin: özel etkinlik, grup bloğu veya bakım gibi durumlar fiyatı etkiler.

Bu içerik taslaktır; operatör incelemesi gerekir.
