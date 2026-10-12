# Mobil premium cihaz kabulü

Bu kabul, **imzalı IPA/APK** üzerinde yapılır. Expo Web, gerçek cihaz kabulünün yerine geçmez.

## Rol matrisi

| Rol | Giriş | Ana görev | Yetkisiz alan | Kanıt |
|---|---|---|---|---|
| Ön büro | Başarılı | Bugün, rezervasyon, check-in | Finans yönetimi | Maestro ekran görüntüsü + QA imzası |
| Kat hizmetleri | Başarılı | Oda durumları ve görevler | Kasa/POS | `role_housekeeping.yaml` |
| Yönetici | Başarılı | Özet ve raporlar | Backend yetkisine göre | `role_manager.yaml` |
| Misafir | Başarılı | Rezervasyon ve servis | Personel alanları | `guest_digital_key.yaml` yalnızca UI render kanıtıdır |

## Cihaz ve erişilebilirlik matrisi

| Hedef | Zorunlu kontrol |
|---|---|
| iPhone güncel iOS | Dynamic Type: Varsayılan ve en büyük metin; VoiceOver odak sırası; koyu/açık tema |
| iPad | Portre + yatay; form içerikleri okunabilir genişlikte; alt sekmeler taşmaz |
| Android telefon | Font size: Varsayılan ve en büyük; TalkBack; çevrimdışı uyarı |
| Android tablet | Portre + yatay; dokunma hedefleri en az 44pt eşdeğeri |

## Gerçek ekran görüntüsü kuralı

`mobile/store/generate_assets.py` yalnızca tasarım/mağaza önizlemesidir. Yayın görseli için:

1. Pilot build'i gerçek cihazda açın ve test verisi içermeyen QA tesisi kullanın.
2. Her rol için yukarıdaki Maestro akışını `SMOKE_*` çevre değişkenleriyle çalıştırın.
3. Oluşan cihaz ekran görüntülerini `artifacts/<build-number>/<device>/<role>/` altında saklayın.
4. Manifestte build numarası, işletim sistemi, cihaz, dil, tema, test hesabı kimliği (e-posta değil) ve test tarihi yer alsın.
5. Misafir adı, telefon, e-posta, folyo veya anahtar verisi görünüyorsa maskeleyin; gerçek üretim verisini mağaza görseli yapmayın.

## Dijital anahtar istisnası

Dijital anahtarın fiziksel kilitte BLE/NFC açma kabulü bu paketin kapsamı dışındadır. Sağlayıcı, kilit modeli, test odası ve denetim kayıtları sağlandığında ayrı donanım pilotunda doğrulanacaktır.
