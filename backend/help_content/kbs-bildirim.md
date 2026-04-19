# KBS — Konaklama Bildirim Sistemi

KBS, Emniyet Genel Müdürlüğü'nün otellerden günlük olarak istediği misafir bildirim sistemidir. Syroce PMS, bu süreci yarı-otomatik olarak yönetir.

## Veri Akışı

1. Check-in sırasında misafir kimlik bilgileri (ad, soyad, T.C. Kimlik No / Pasaport No, doğum tarihi, uyruk) otomatik toplanır.
2. **KBS** ekranında o günün bildirilecek misafir listesi görüntülenir.
3. Yardımcı KBS masaüstü uygulaması, PMS kullanıcı oturumuyla giriş yaparak listeyi çeker ve EGM sistemine iletir.
4. Başarılı bildirim sonrası rapor numarası ile birlikte sistemde "bildirildi" işareti konulur.

## Önemli Noktalar

- **Anonim misafir kabul edilmez**: kimlik bilgisi eksik check-in'ler bildirim listesine düşer; sistem uyarı verir.
- **Tarih gecikmesi**: aynı gün bildirilmeyen misafirler için sistem dashboard'da "Geç KBS" sayacı gösterir.
- **Kullanıcı izolasyonu**: her oda kullanıcısı yalnızca kendi otelinin verisini görür; KBS API key dağıtmaya gerek yoktur.

## Geçmiş Raporlar

**KBS > Geçmiş Raporlar** sekmesinden hangi gün hangi misafirlerin bildirildiği, toplam sayı ve EGM yanıt referansları görüntülenebilir.
