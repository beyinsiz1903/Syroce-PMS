# Mobil smoke testleri (Maestro)

Bu klasör, EAS preview/production build'leri TestFlight veya Play Internal
testing'e yüklenmeden önce çalıştırılan minimal regresyon akışlarını içerir.

Amaç: en sık bozulan kullanıcı yollarını otomatik doğrulamak —
**login → Bugün açılışı → Hızlı check-in başlangıcı → Dijital anahtar
görüntüleme**. Akışlar başarısız olursa kötü bir build iç test
kullanıcılarına dağıtılmadan yakalanır.

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

| Dosya                                | Senaryo                                 | Rol         |
| ------------------------------------ | --------------------------------------- | ----------- |
| `flows/login.yaml`                   | Uygulamayı sıfırla, login formu, gönder | Tüm roller  |
| `flows/frontdesk_today.yaml`         | Login + "Bugün" tabı yüklenir           | front_desk  |
| `flows/frontdesk_quick_checkin.yaml` | Login + Hızlı check-in başlat           | front_desk  |
| `flows/guest_digital_key.yaml`       | Login + dijital anahtar ekranı render   | guest_app   |

`login.yaml` `runFlow` ile diğerlerinden çağrılır — tek kaynaktan
korunur.

## Cihaz seçimi

Maestro varsayılan olarak çalışan tek bir simülatör/emülatör algılar.
Birden fazla cihaz açıksa `MAESTRO_DEVICE` env değişkeni ile belirtin
(örn. `MAESTRO_DEVICE=emulator-5554 npm run smoke`) veya
`maestro --device <id> test ...` kullanın.

## Sorun giderme

| Belirti                                       | Çözüm                                                       |
| --------------------------------------------- | ----------------------------------------------------------- |
| `maestro: command not found`                  | Yukarıdaki kurulum adımı + `~/.maestro/bin` PATH'e ekle.    |
| "No connected devices found"                  | iOS Simulator veya Android Emulator açın, build'i yükleyin. |
| `assertVisible` "Giriş Yap" timeout           | Build start'ı yapamadı — workflow logs / cihaz logu kontrol.|
| `openLink` "syrocepms:///" tetiklenmiyor      | `app.json` → `expo.scheme` "syrocepms" mi kontrol edin.     |
| Login `401`                                   | Demo kimlik bilgilerini güncelleyin veya env override edin. |
