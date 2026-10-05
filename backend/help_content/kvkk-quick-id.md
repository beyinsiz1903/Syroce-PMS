# KVKK & Quick-ID Kimlik Fotoğrafları

Quick-ID, kimlik ve pasaport görüntüsünden misafir alanlarını çıkarıp kullanıcı onayına sunar. Tarama görüntüsü ve ham OCR metni Quick-ID tarama akışında saklanmaz.

## Quick-ID Mimarisi

- **Varsayılan yerleşik mod**: OCR, PMS backend içinde çalışır; ikinci bir servis veya herkese açık Quick-ID adresi gerekmez
- **Opsiyonel ayrı servis**: `QUICKID_MODE=external`, `QUICKID_URL` ve `QUICKID_SERVICE_KEY` tanımlanırsa mevcut servis anahtarlı proxy yolu kullanılır
- **Sağlayıcılar**: OpenAI/Gemini vision veya konteyner içindeki ücretsiz Tesseract
- **Kaynak koruması**: görüntü boyutu, zaman aşımı ve eşzamanlı tarama sınırları uygulanır

## Veri Akışı

1. Misafir online check-in'de fotoğraf yükler veya resepsiyonist çeker
2. PMS backend görüntüyü bellekte işler veya seçilen vision sağlayıcısına gönderir
3. Çıkarılan alanlar kullanıcıya doğrulama için gösterilir; kullanıcı kabul etmeden rezervasyona yazılmaz
4. Kabul edilen alanlar mevcut PMS alan şifreleme politikasıyla misafir ve rezervasyon kaydına işlenir
5. Tarama görüntüsü ve sağlayıcının ham metni cevapta veya veritabanında tutulmaz

## Erişim Kontrolü

- Tarama uç noktası yalnızca oturum açmış PMS kullanıcılarına açıktır
- Sağlayıcı anahtarları tarayıcıya gönderilmez; PMS içinde şifreli ayarlardan veya ortam değişkenlerinden okunur
- Tarama, KVKK onay kutusunu otomatik işaretlemez; açık rıza/aydınlatma akışı kullanıcı tarafından tamamlanır

## Saklama Süresi

Quick-ID tarama görüntüsünü saklamaz. Kullanıcı tarafından onaylanıp PMS'e yazılan kimlik alanları, PMS'in mevcut yasal saklama ve anonimleştirme kurallarına tabidir.

## İlgili Raporlar

- **Bekleyen Kimlik Fotoğrafları**: henüz yüklenmemiş check-in'ler
- **Kimlik Fotoğrafı Görüntüleme Raporu**: KVKK denetim için kim ne zaman ne gördü
- **Geri Alınan Mesajlar Raporu**: hatalı paylaşımlar

## Demo Modu

`ENABLE_QUICKID_DEMO=true` set ise demo tenant'lar için sahte fotoğraflar üretilir; **üretimde kapalı** olmalıdır.

## KVKK Uyum Önerileri

- KVKK Sorumlusu / DPO atayın ve rolünü tanımlayın
- Misafire **aydınlatma metni** check-in'de gösterin (online check-in formunda otomatik)
- Veri ihlali durumunda 72 saat içinde KVKK Kurumu'na bildirim yapın
- Yıllık VERBİS güncellemesi yapın
