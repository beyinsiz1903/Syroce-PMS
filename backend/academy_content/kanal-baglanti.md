# OTA Bağlantıları ve Senkron

Channel Manager (CM), oteli OTA kanallarına (Booking, Expedia vb.) bağlar ve müsaitlik/fiyat/rezervasyon akışını senkronize eder.

## Bağlantı kurulumu

- Her tesis için **tek bir CM sağlayıcısı** tanımlıdır (örn. Exely veya HotelRunner).
- Bağlantı, sağlayıcıya özel kimlik/anahtarlarla yapılandırılır; eksik yapılandırmada işlem fail-closed olur.
- İstemci tarafı sağlayıcıyı geçersiz kılamaz; sabitlenmiş sağlayıcı esastır.

## Rezervasyon akışı (inbound)

- OTA'dan gelen rezervasyon webhook ile alınır ve PMS'e düşer.
- Eşleşmeyen rezervasyon **bekletme (hold)** olarak işaretlenir ve operatör uyarılır.
- Webhook kaynağı kimlik doğrulamasından geçer; sahte çağrı kabul edilmez.

## Senkron (outbound)

- Müsaitlik ve fiyat güncellemeleri kanallara gönderilir.
- Bağlantı sorunlarında devre kesici (circuit breaker) devreye girer; tekrar denemeler sınırlıdır.

> Stop-sale ve no-show gibi durumlar kanallara yansıtılır. Senkron hatası sessizce yok sayılmaz; çakışma kuyruğunda toplanır.

Bu içerik taslaktır; operatör incelemesi gerekir.
