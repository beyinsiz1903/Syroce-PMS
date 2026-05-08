# Oda QR Talepleri

Her odada bulunan benzersiz QR kodu, misafire kâğıtsız self-service bir talep / hizmet kanalı sunar.

## QR Üretimi

**Yönetim > Oda Tipleri > QR Etiketleri** üzerinden oda bazlı QR PDF'i üretilir. QR içinde imzalı bir token (`ROOM_QR_SECRET` ile imzalı) vardır — başkası tarafından kopyalansa bile güvenli, oda bazlı tek geçer.

## Misafir Tarafı

Misafir QR'ı tarar → mobil uyumlu menü açılır:

- **Housekeeping** isteği (havlu, amenities, geç temizlik)
- **Bakım** bildirimi (bkz. [Bakım İş Emirleri](#/help/maintenance))
- **Room Service** sipariş
- **Spa / Restoran** rezervasyon
- **Folio görüntüleme** ve check-out
- **Online check-in** linki
- **Misafir Anketi** (NPS — bkz. [Audit Timeline](#/help/audit-log))

Misafir giriş yapmaz; QR token oturum açar.

## Personel Tarafı

İstekler ilgili departmanın dashboard'una düşer; hedef yanıt süresi (SLA) departmana göre tanımlıdır:

- Housekeeping: 15 dk
- Bakım acil: 10 dk
- Room service: 30 dk

SLA aşımları kırmızı vurgulanır ve yöneticiye bildirim düşer.

## Güvenlik

- QR token imzası `ROOM_QR_SECRET` ile doğrulanır; geçersiz/değiştirilmiş token reddedilir.
- Aynı oda için bir önceki misafir check-out olduğunda token rotasyon otomatik (yenisi yazdırılır).
- Misafir kendi adisyonu/folio'su dışındaki bilgileri **göremez**; multi-tenant izolasyon korunur.

## İstatistik

QR talep hacmi, kategori dağılımı, ortalama yanıt süresi **Misafir Deneyimi Dashboard**'da raporlanır.
