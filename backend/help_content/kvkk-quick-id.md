# KVKK & Quick-ID Kimlik Fotoğrafları

KVKK (6698 sayılı Kişisel Verilerin Korunması Kanunu) ve GDPR uyumu için, misafir kimlik fotoğrafları izole bir mikro-servis olan **Quick-ID** üzerinde şifreli saklanır.

## Quick-ID Mimarisi

- **Ayrı servis**: ana PMS'den bağımsız; `QUICKID_URL` ortam değişkeniyle bağlanır
- **Servis kimliği**: `QUICKID_SERVICE_KEY` ile bütün çağrılar imzalanır (mTLS benzeri korumalı)
- **AES-256-GCM** ile fotoğraflar at-rest şifrelenir
- **Tenant izolasyonu**: her otelin verileri ayrı namespace'te tutulur, cross-tenant okuma teknik olarak imkânsız

## Veri Akışı

1. Misafir online check-in'de fotoğraf yükler veya resepsiyonist çeker
2. PMS fotoğrafı **base64'le Quick-ID'ye yollar**, geriye yalnızca **referans token** alır
3. PMS veritabanında **fotoğraf yok**, yalnızca token saklanır
4. Görüntüleme zamanı: yetkili kullanıcı tıklar, PMS Quick-ID'den token + zaman damgası ile fotoğrafı çeker, **anlık olarak** kullanıcıya stream eder
5. Kullanıcı sayfayı kapatınca cache'lenmez

## Erişim Kontrolü

- Yalnızca **GM, Ön Büro Müdürü, KVKK Sorumlusu** rolleri görüntüleyebilir
- Her görüntüleme **audit log**'a yazılır (kim / ne zaman / hangi misafir / hangi cihaz)
- Aynı kullanıcı belirli süre içinde aşırı sayıda görüntüleme yaparsa (`KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`) yöneticiye uyarı düşer

## Saklama Süresi

- **Aktif misafir**: konaklama süresi + 30 gün
- **KBS bildirimi tamamlandıysa** ve yasal saklama süresi dolduysa otomatik silinir (cron)
- Misafir KVKK kapsamında **silinme talebi** verirse manuel silme arabirimi mevcuttur (yönetici onayı gerekir)

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
