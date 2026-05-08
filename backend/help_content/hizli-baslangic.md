# Hızlı Başlangıç Rehberi

Syroce PMS'ye hoş geldiniz. Bu rehber, sistemi ilk defa kullanan kullanıcılar için temel adımları özetler.

## 1. Giriş Yapma

Otel kodunuz, kullanıcı adınız ve şifrenizle giriş yapın. **İki faktörlü doğrulama (2FA/TOTP)** etkinse, telefon uygulamasından (Google Authenticator, 1Password, Authy vb.) gelen 6 haneli kodu da girmeniz istenir. Yetkili kullanıcılar için 2FA önerilmez — **zorunludur**. Ayrıntı: [2FA Etkinleştirme](#/help/2fa-totp).

## 2. Ana Pano (Dashboard)

Giriş sonrası karşınıza çıkan **Dashboard**'da güncel doluluk, günün gelen-giden misafir sayısı, bugünkü ciro, operasyonel uyarılar, KPI kartları (intent renkli — bilgi/başarı/uyarı/tehlike) ve hızlı aksiyonlar yer alır.

## 3. Üst Menü (Top Navigation)

Üst menü 7 ana grup + sağda kullanıcı menüsünden oluşur:

- **Rezervasyon**: Takvim, yeni rezervasyon, grup rezervasyon, gelenler/gidenler
- **Finans**: Folio, kasa/POS, konaklama vergisi, fiyat planları
- **Kanallar**: OTA bağlantıları, channel manager (Exely, HotelRunner), rate manager
- **Raporlar**: Doluluk, ADR, RevPAR, mevzuat raporları, özel rapor builder
- **Gelişmiş**: AI / RMS dashboard, dinamik fiyat, tahminleme, upsell
- **Yönetim**: Kullanıcılar, roller, oda tipleri, İK, ayarlar
- **Altyapı**: Audit timeline, güvenlik, entegrasyon sağlığı

Sağda dil seçici (TR/EN), bildirim çanı, kullanıcı menüsü ve "Push kapalı/açık" indikatörü vardır.

## 4. Sık Kullanılan Sayfalar

- **Operasyon**: PMS, takvim, housekeeping, bakım iş emirleri, vardiya devri
- **Misafir**: Online check-in, dijital anahtar, oda QR talepleri, kayıp eşya
- **Finans**: Folio, kasa, erken/geç çıkış ücretleri, konaklama vergisi
- **Mevzuat**: KBS, TÜİK, yıldız sınıflama self-check

## 5. İpuçları

- Üst arama kutusu rezervasyon, misafir, oda numarası, fatura no üzerinden hızlı arama yapar.
- **Yardım merkezi**: üst menüden veya `/app/help` üzerinden tüm makalelere ulaşabilirsiniz; arama en az 2 harfle çalışır.
- **Audit Timeline**: tüm önemli işlemler kim/ne/ne zaman olarak kaydedilir; sağ kenardaki tarih ikonundan açılır. Ayrıntı: [Audit Timeline](#/help/audit-log).
- **In-app diyaloglar**: silme/onay işlemleri tarayıcının yerleşik `confirm`/`alert` yerine uygulama içi modal kullanır.
- **Dil değişimi**: sağ üstteki "TR Türkçe" rozetinden TR/EN/RU vb. anında geçilir; tercih kullanıcıya bağlı saklanır.

## Sonraki Adımlar

- [Rezervasyon Oluşturma](#/help/rezervasyon-olusturma)
- [Check-in / Check-out Akışı](#/help/check-in-checkout)
- [Konaklama Vergisi Beyannamesi](#/help/konaklama-vergisi)
- [Channel Manager (OTA)](#/help/channel-manager)
- [RMS Dashboard (AI)](#/help/rms-dashboard)
- [Kullanıcı Rolleri ve Yetkilendirme](#/help/kullanici-rolleri)
