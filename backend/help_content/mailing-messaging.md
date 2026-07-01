# Mailing & Mesajlaşma (Outbound)

Misafire ve operasyona yönelik tüm dış iletişim — e-posta, SMS, in-app mesaj — tek panelden yönetilir.

## Tetikleyiciler

| Olay | Otomatik Mesaj |
|------|---------------|
| Rezervasyon onaylandı | Onay e-postası + iCal eki |
| Check-in 24 saat öncesi | Online check-in linki |
| Check-out sonrası | NPS / yorum daveti |
| İptal | İade detayı |
| Doğum günü | Doğum günü kuponu |
| VIP geliyor | İç bildirim — GM'e push |

## Şablonlar

**Yönetim > Ayarlar > Mesajlaşma Şablonları**:

- Çok dilli (TR, EN, RU, AR, DE)
- Değişken yer tutucular (`{{misafir_adi}}`, `{{oda_no}}`, `{{toplam}}`)
- Önizleme + test gönderim

## Sağlayıcılar

- **E-posta**: Resend (`RESEND_API_KEY`, `RESEND_FROM` ortam değişkenleri)
- **SMS**: Tenant bazlı entegrasyon (NetGSM, İletimerkezi vb.)
- **In-app**: Native push (Expo) + WebSocket

## Dashboard

**Mesajlaşma Dashboard**'da:

- Bugün gönderilen mesaj sayısı (yöntem dağılımı)
- Bounce / Failed oranı
- Açılma / tıklama oranı (e-posta için)
- Acil mesaj havuzu

## Acil / Geri Alınan Mesajlar

- **Acil mesaj**: yetkili kullanıcılar (GM, ön büro müdürü) tüm aktif kullanıcılara anlık bildirim gönderebilir. **Acil Mesaj İzinleri** ekranından kim yetkili tanımlanır.
- **Geri Alınan**: yanlış gönderim için "geri al" butonu mevcut; geri alınan mesajlar **Geri Alınan Mesajlar Raporu**'nda izlenir.

## KVKK & İzin

- Misafire pazarlama amaçlı mesaj göndermeden önce **rıza onayı** kayıtlı olmalıdır.
- Misafir "Beni listenden çıkar" tıkladığında otomatik unsubscribe; sonrası mesaj gönderilemez.

## Toplu Kampanya

**Mailing > Yeni Kampanya** ile filtre tabanlı (uyruk, sadakat seviyesi, son kalış tarihi) gönderim. **Promise.allSettled** kullanır — bireysel hata kampanyayı durdurmaz.
