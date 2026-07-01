# Fiyat/Müsaitlik ve Rate Parity

Kanallara doğru fiyat ve müsaitlik göndermek, hem geliri hem de kanal ilişkilerini korur.

## Müsaitlik yönetimi

- Müsaitlik, oda tipi bazında yönetilir ve birleşik (unified) rate manager üzerinden kanallara dağıtılır.
- Kontenjan (allotment) ile kanallara ayrılan oda sayısı kontrol edilir.
- Aşırı satışı (overbooking) önlemek için müsaitlik gerçek envantere dayanır.

## Fiyat dağıtımı

- Fiyat güncellemeleri **oda tipi bazında** yapılır; tek fiyatın tüm tiplere uygulanması yanlış paritedir.
- Toplu güncelleme (bulk grid update) ile tarih aralığı ve oda tipleri birlikte güncellenir.

## Rate parity

- Parite, aynı oda tipinin kanallar arası fiyat tutarlılığıdır.
- Analitik, oda tipi başına karşılaştırma yapar; farklı tipleri kıyaslamak yanlış parite sinyali verir.

> Analitikteki bazı eski "fiyat güncelle/müsaitlik gönder" ekranları yalnızca niyet kaydı tutar; gerçek OTA push birleşik rate manager üzerinden yapılır.

Bu içerik taslaktır; operatör incelemesi gerekir.
