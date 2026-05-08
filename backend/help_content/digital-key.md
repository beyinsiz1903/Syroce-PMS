# Dijital Anahtar & Mobil Uygulamalar

Misafir, mobil uygulamayla (iOS / Android — Expo tabanlı) cep telefonunu **oda anahtarı** olarak kullanabilir; resepsiyona uğramadan direkt odaya geçebilir.

## Akış

1. Misafir uygulamayı indirir, e-posta + rezervasyon kodu ile giriş yapar.
2. **Online check-in** tamamlandıktan sonra (bkz. [Online Check-in](#/help/online-checkin)) mobil anahtar **ödenmiş ve onaylı** rezervasyonlar için aktif olur.
3. Misafir oda kapısına yaklaşıp **Bluetooth/NFC** ile kilidi açar (veya QR tarama destekli kapılarda QR ile).
4. Anahtar yetkisi check-out tarihinde otomatik iptal olur.

## Misafir Mobil Uygulaması Özellikleri

- Rezervasyon listesi
- Folio görüntüleme + ödeme
- Room service / housekeeping istekleri
- Otel haritası, restoran menüleri, spa rezervasyon
- Push bildirimleri (oda hazır, mesaj geldi)

## Personel Mobil Uygulaması

- **Housekeeping görevleri** + checklist
- **Bakım iş emirleri** + foto yükleme
- **VIP misafir uyarıları** (yaklaşan check-in)
- **Acil mesajlar** (vardiya değişim notu)

## Push Bildirim

`DISABLE_EXPO_PUSH` ortam değişkeni `false` ise Expo Push servisi aktif. Üst menü sağında **Push açık/kapalı** indikatörü görünür. Tarama frekansı `MOBILE_PUSH_SCAN_SECONDS` ile ayarlanır; VIP misafir penceresi `MOBILE_PUSH_VIP_WINDOW_MINUTES`.

## Güvenlik

- Anahtar token **device-bound** ve **time-bound** (sadece check-in/out aralığında geçerli)
- Telefon kaybı durumunda misafir resepsiyondan veya uygulamadan **anahtarı iptal edebilir**
- Tüm açma denemeleri **audit log**'a yazılır

## Sınırlamalar

- Yalnızca BLE/NFC destekli akıllı kilit donanımına sahip odalarda kullanılır
- Standart kilitli odalar için fiziksel kart anahtar veya kart kopyalama desteği devam eder
