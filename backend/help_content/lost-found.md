# Kayıp Eşya Yönetimi

Misafirlerin otelde unuttuğu veya bulunan eşyaların kayıt, depolama ve teslim sürecini yönetir.

## Eşya Kaydı

Eşya bulunduğunda **Kayıp Eşya > Yeni Kayıt**:

- **Bulunduğu yer** (oda no, restoran, lobi, havuz vb.)
- **Bulan personel** (otomatik mevcut kullanıcı)
- **Eşya türü** (giysi, takı, elektronik, doküman, diğer)
- **Açıklama** (renk, marka, ayırıcı özellik)
- **Fotoğraf** (zorunlu — KVKK kapsamında saklama süresi 90 gün)
- **Depolama yeri** (kasa, depo rafı no)
- **Yaklaşık değer** (sigorta için)

Sistem benzersiz bir **Kayıt No** üretir ve etiket (QR + barkod) yazdırma sunar.

## Misafire Bildirim

Eşya, son ayrılan misafirin rezervasyonuyla otomatik eşleşirse sisteme **"Bilgilendir"** butonuyla e-posta/SMS gönderilebilir: "Otelimizde eşyanızı unuttunuz; teslim almak için bizi arayın."

## Teslim

Misafir aldığında:

1. Kimlik kontrolü
2. **Teslim Tutanağı** otomatik oluşturulur (misafir adı + imza alanı)
3. Eşya durumu **"Teslim Edildi"** olur

## Kargo

Misafir uzakta ise kargo bilgileri girilir (kargo firması, takip no, ücret tarafı). Sistem misafire takip linki gönderir.

## Süre Doldu

90 gün boyunca alınmayan eşya için:

- Tutanakla **bağışlanabilir** (yetkili imzasıyla)
- Tutanakla **imha edilebilir** (gıda/değersiz)
- Yüksek değerli eşya **emanet kasasına** taşınır, hukuk birimine yönlendirilir

## Boş Liste

Henüz eşya yoksa "İlk kaydı oluşturmak için **+ Yeni Kayıt**'a tıklayın" CTA'sı görünür.
