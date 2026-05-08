# Online Check-in (Self-Service)

Misafirler, otele varmadan önce kendi cihazlarından **pre-check-in** yaparak resepsiyondaki bekleme süresini kısaltabilir.

## Nasıl Çalışır

1. Rezervasyon onaylandığında misafire **e-posta + SMS** ile kişisel link / QR gönderilir.
2. Misafir linke tıklar; mobil uyumlu form açılır.
3. Misafir **kimlik bilgilerini** (T.C. Kimlik No / Pasaport No, doğum tarihi, uyruk), **iletişim** ve **özel istek**'leri (geç giriş, ekstra yastık vb.) girer.
4. **Kimlik fotoğrafı yükler** (KVKK kapsamında şifrelenir; bkz. [KVKK & Quick-ID](#/help/kvkk-quick-id)).
5. Misafir varış saatini onaylar.
6. Resepsiyon ekranında bu rezervasyon **"Online Check-in Tamamlandı"** rozetiyle yeşil işaretlenir.

## Resepsiyonda

- Misafir geldiğinde yalnızca **kimlik doğrulaması + oda anahtarı** verilir; tüm form alanları zaten dolu.
- Misafirin yüklediği kimlik fotoğrafı, KVKK'ya uyum amacıyla yetkili kullanıcı tarafından onaylanır (her görüntüleme **audit log**'a yazılır).

## Yapılandırma

**Yönetim > Ayarlar > Online Check-in** ekranından:

- Linkin gönderileceği gün (varsayılan: check-in tarihinden 24 saat önce)
- Zorunlu alanlar (kimlik, fotoğraf, imza)
- Garanti yöntemi (kredi kartı pre-auth) zorunlu mu

## Sınırlamalar

- Grup rezervasyonlarında her misafir ayrı link alır.
- Aynı rezervasyon için birden fazla misafir varsa her biri ayrı form doldurur.
- Misafir 2 kez denedikten sonra link iptal olur (dolandırıcılık koruması).
