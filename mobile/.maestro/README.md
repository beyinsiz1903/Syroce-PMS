# Mobil smoke testleri (Maestro)

Bu klasör, EAS preview/production build'leri TestFlight veya Play Internal
testing'e yüklenmeden önce çalıştırılan minimal regresyon akışlarını içerir.

Amaç: en sık bozulan kullanıcı yollarını otomatik doğrulamak —
**login → Bugün açılışı → Hızlı check-in başlangıcı → Dijital anahtar
görüntüleme → push kaydı → biyometrik kilit → çevrimdışı önbellek**.
Akışlar başarısız olursa kötü bir build iç test kullanıcılarına
dağıtılmadan yakalanır.

## Maestro nedir?

[Maestro](https://maestro.mobile.dev) yerel olarak iOS Simulator,
Android Emulator veya gerçek cihaz üzerinde çalışan YAML tabanlı bir
mobil UI test koşucusudur. Native build değişikliği gerektirmez,
managed Expo projeleri için uygundur.

## Kurulum (yerel makine)

```bash
# macOS / Linux
curl -fsSL "https://get.maestro.mobile.dev" | bash
# veya brew ile
brew tap mobile-dev-inc/tap && brew install maestro
```

Sonrasında `~/.maestro/bin` PATH'e eklenmelidir (yükleyici hatırlatır).
Kurulum doğrulama:

```bash
maestro --version
```

## Çalıştırma

EAS build dev client veya store imzalı IPA/APK simülatöre/emülatöre
yüklendikten sonra:

```bash
cd mobile
npm run smoke
```

Belirli bir akış için (üçü de eşdeğer):

```bash
npm run smoke -- frontdesk_quick_checkin.yaml
npm run smoke -- .maestro/flows/frontdesk_quick_checkin.yaml
maestro test .maestro/flows/frontdesk_quick_checkin.yaml
```

> CI veya gerçek QA koşusunda **demo hesabı varsayılanını kullanmayın** —
> aşağıdaki env değişkenlerini her zaman override edin.

## Kimlik bilgileri

Varsayılan olarak demo hesabı (`info@syroce.com / Syroce2026`) kullanılır.
Üretim build'ini test ederken gerçek hesap bilgilerini env değişkenleri
ile geçin:

```bash
SMOKE_EMAIL=qa-frontdesk@syroce.com \
SMOKE_PASSWORD=*** \
SMOKE_GUEST_EMAIL=qa-guest@syroce.com \
SMOKE_GUEST_PASSWORD=*** \
npm run smoke
```

`scripts/smoke.sh` bu env değişkenlerini Maestro'ya `-e` ile aktarır.

## Akışlar

| Dosya                                | Senaryo                                                       | Rol         |
| ------------------------------------ | ------------------------------------------------------------- | ----------- |
| `flows/login.yaml`                   | Uygulamayı sıfırla, login formu, gönder                       | Tüm roller  |
| `flows/frontdesk_today.yaml`         | Login + "Bugün" tabı yüklenir                                 | front_desk  |
| `flows/frontdesk_quick_checkin.yaml` | Login + Hızlı check-in başlat                                 | front_desk  |
| `flows/guest_digital_key.yaml`       | Login + dijital anahtar ekranı render                         | guest_app   |
| `flows/push_register.yaml`           | Login + "Daha" sekmesinde push bildirim göstergesi görünür    | front_desk  |
| `flows/biometric_lock.yaml`          | Biyometrik kilidi aç → background → foreground → kilit göster | front_desk  |
| `flows/offline_today.yaml`           | Login + Bugün cache + uçak modu + OfflineBanner doğrulanır    | front_desk  |

`login.yaml` `runFlow` ile diğerlerinden çağrılır — tek kaynaktan
korunur. `biometric_lock.yaml` ve `offline_today.yaml` ek olarak
`scripts/*.js` shell köprüsünü kullanır (aşağıdaki "Önkoşullar"
bölümüne bakın).

## Yeni akışlar için önkoşullar

### `push_register.yaml`

Bir EAS dev-client / production build çalışıyor olmalı (Expo Go
SDK 53+ remote push'u kısıtlar). Cihaz/emülatörün bildirim izni
verme ekranı çıkarsa Maestro bunu otomatik kabul eder
(`launchApp.permissions.all=allow`). Asser çıktısı iki olabilir:

- **"Açık"** — token alındı ve `/api/notifications/push/register`'a
  POST edildi (asıl prod doğrulaması).
- **"Kapalı / Devre dışı"** — kayıt akışı çalıştı fakat OS izin
  vermedi ya da simülatör push entitlement'i yok. Yine de regresyon
  kapsamı korunur (göstergenin hiç oluşmaması bug sayılır).

### `biometric_lock.yaml` (Android emulator)

`scripts/simulate_fingerprint.js` `adb emu finger touch 1` komutunu
çalıştırır. Bu yüzden:

1. Android emulator açın (Pixel 7 API 34 önerilir).
2. **Settings → Security & privacy → Fingerprint** üzerinden id `1`
   ile parmak izi kaydedin (kaydetme akışında `adb -e emu finger touch 1`
   ile sahte taramayı tetikleyebilirsiniz).
3. `npm run smoke -- biometric_lock.yaml` çalıştırın.

iOS Simulator'de Face ID/Touch ID `xcrun simctl ui` ile tetiklenir;
mevcut script Android-only'dir, iOS'ta manuel test gereklidir.

### `offline_today.yaml` (Android emulator)

`scripts/disable_network.js` ve `enable_network.js` `adb shell svc wifi`
ile uçak modunu taklit eder. CI'de:

- `adb` PATH'te olmalı (Maestro JVM'inden erişilebilir).
- Tek bir cihaz bağlı olmalı veya `ANDROID_SERIAL` set edilmeli.
- Test sonrası `enable_network.js` ağı geri açar; başarısız olursa
  emulator yeniden başlatılarak temizlenir.

iOS Simulator'de eşdeğer CLI yok — testin `runScript` adımı no-op
olarak loglanır ve ağı manuel olarak Settings'ten kapatmanız beklenir.

## Cihaz seçimi

Maestro varsayılan olarak çalışan tek bir simülatör/emülatör algılar.
Birden fazla cihaz açıksa `MAESTRO_DEVICE` env değişkeni ile belirtin
(örn. `MAESTRO_DEVICE=emulator-5554 npm run smoke`) veya
`maestro --device <id> test ...` kullanın.

## Sorun giderme

| Belirti                                                    | Çözüm                                                                                  |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `maestro: command not found`                               | Yukarıdaki kurulum adımı + `~/.maestro/bin` PATH'e ekle.                               |
| "No connected devices found"                               | iOS Simulator veya Android Emulator açın, build'i yükleyin.                            |
| `assertVisible` "Giriş Yap" timeout                        | Build start'ı yapamadı — workflow logs / cihaz logu kontrol.                           |
| `openLink` "syrocepms:///" tetiklenmiyor                   | `app.json` → `expo.scheme` "syrocepms" mi kontrol edin.                                |
| Login `401`                                                | Demo kimlik bilgilerini güncelleyin veya env override edin.                            |
| `push_register` "smoke-push-status" timeout                | EAS dev-client build çalıştığını ve Daha sekmesinin render olduğunu doğrulayın.        |
| `biometric_lock` "Doğrulama gerekli" timeout               | Emulator'de parmak izi enroll değil veya `adb emu finger touch 1` çalışmadı (logları kontrol). |
| `offline_today` "Bağlantı kurulamadı" timeout              | `adb shell svc wifi disable` reddedildi (root yok) — emulator dışında test ediyorsunuz.|
| `offline_today` sonrası ağ kapalı kaldı                    | Manuel `adb shell svc wifi enable` veya emulator'ı yeniden başlatın.                   |
