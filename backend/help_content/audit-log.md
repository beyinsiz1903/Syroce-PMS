# Audit Timeline (Denetim Zaman Çizelgesi)

Sistemdeki **tüm önemli işlemler** kim / ne / ne zaman / hangi cihaz / hangi IP bilgileriyle değiştirilemez şekilde kaydedilir.

## Neler Loglanır?

- **Auth**: giriş, çıkış, başarısız giriş, 2FA etkinleştirme/sıfırlama, parola değişikliği
- **Rezervasyon**: oluşturma, düzenleme, iptal, oda değişimi
- **Folio**: adisyon ekleme, void, transfer, bölme, fatura kesme
- **Ödeme**: tahsilat, iade, kasa farkı
- **Yönetim**: kullanıcı/rol değişiklikleri, ayar değişiklikleri (vergi oranı, fiyat kuralları), tenant ayarları
- **KVKK**: kimlik fotoğrafı görüntüleme, silme talepleri (bkz. [KVKK & Quick-ID](#/help/kvkk-quick-id))
- **Mevzuat**: KBS bildirim, beyanname kilitleme, TÜİK rapor üretimi
- **Entegrasyon**: OTA push/pull, webhook tetikleme, SXI olay yayınlama

## Erişim

İki yoldan açılır:

1. **Sağ kenardaki tarih ikonu** — bağlamsal Audit Drawer (görüntülenen kayıt için geçmiş)
2. **Altyapı > Denetim Zaman Çizelgesi** — tam ekran filtreli liste

## Filtreleme

- Tarih aralığı
- Kullanıcı (ad, e-posta)
- Olay türü (auth, finans, kvkk vb.)
- Entity (rezervasyon ID, folio ID, oda no)
- Sonuç (başarılı / başarısız)
- IP adresi

## Snapshot Diff

Bir kaydın geçmişine bakarken sistem **eski → yeni** alan farklarını yan yana gösterir (örnek: oda numarası 305 → 401, fiyat 1.200 → 1.500). Hangi alanın ne zaman değiştiği görsel olarak vurgulanır.

## Değişmezlik (Tamper Evident)

- Audit kayıtları **append-only**; düzenlenemez veya silinemez
- Hash zinciri (her kayıt bir öncekinin hash'ini içerir) ile manipülasyon tespiti
- Yedekleme MongoDB Atlas + günlük snapshot

## Saklama Süresi

- Standart: **7 yıl** (Türkiye Vergi Usul Kanunu uyumu için)
- KVKK kapsamında PII silinse bile audit kaydı silinmez; yalnızca silme **olayı** loglanır

## Dışa Aktarım

Resmî denetim talebine hazır:

- **CSV** / **JSON** indirme
- **Tarih + kullanıcı imzalı** PDF tutanak (mahkeme/vergi denetimi için)

## Pratik İpuçları

- Şüpheli işlem? Önce **kullanıcı bazlı filtre** + tarih aralığı → tüm hareketleri tek bakışta gör
- "Bu rezervasyon kim oluşturdu?" → rezervasyon ekranında üst menü > **Geçmiş**
- Her hata bildiriminde audit kaydının **ID**'si log'da görünür; destek isterken bu ID'yi paylaşın
