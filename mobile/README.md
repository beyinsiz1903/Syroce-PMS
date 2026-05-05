# Syroce PMS Mobil

Expo + React Native + TypeScript ile Syroce PMS'in resmi mobil istemcisi.
Tek kod tabanı resepsiyon, kat hizmetleri, GM ve misafir uygulaması olarak
çalışır; iç dağıtım için iOS TestFlight ve Android Play Internal Testing
hedeflenir.

## Hızlı başlangıç (geliştirme)

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL="https://<replit-dev-domain>" npx expo start
```

`EXPO_PUBLIC_API_URL` arka uç (FastAPI, port 8000) için temel URL. Yerel
geliştirmede Replit dev domain'ini kullanın; backend `/api/...` ön ekiyle
yanıt verir.

`EXPO_PUBLIC_QUICKID_URL` Quick-ID kimlik tarama servisi (varsayılan
aynı host, port `8099`). Üretimde ters proxy üzerinden yayınlanmalıdır.

### Demo hesabı

- `info@syroce.com` / `Syroce2026`

## Kapsam

- JWT login + secure-store oturum, biyometrik kilit (Face ID / parmak izi)
- Rol tabanlı tab navigation: `front_desk`, `housekeeping`, `gm`, `guest_app`
- Resepsiyon "Bugün", hızlı check-in (QR + kimlik tarama → Quick-ID), hızlı
  check-out, walk-in 30 sn akışı, misafir profili
- Kat hizmetleri oda listesi + uzun bas → durum değiştir
- Misafir uygulaması: rezervasyonlarım, dijital anahtar, mesajlaşma,
  oda servisi, sadakat
- V2: çevrim dışı önbellek (TanStack Query persister + MMKV/AsyncStorage)
- V3: SSL pinning (`react-native-ssl-pinning`), push bildirimleri

Karanlık mod ve Türkçe arayüz desteklenir; emoji kullanılmaz.

## Mağaza varlıkları

Tüm icon, splash ve mağaza ekran görüntüleri `mobile/assets/` ve
`mobile/store/screenshots/` altındadır. Üretmek/güncellemek için:

```bash
cd mobile
python3 store/generate_assets.py
```

Ayrıntı: [`store/README.md`](store/README.md).

| Asset                              | Boyut       | Kullanım                          |
| ---------------------------------- | ----------- | --------------------------------- |
| `assets/icon.png`                  | 1024 × 1024 | iOS app icon, genel               |
| `assets/adaptive-icon.png`         | 1024 × 1024 | Android adaptive foreground       |
| `assets/splash-light.png`          | 1242 × 2436 | Açılış ekranı (açık şema)         |
| `assets/splash-dark.png`           | 1242 × 2436 | Açılış ekranı (karanlık şema)     |
| `assets/notification-icon.png`     | 96 × 96     | Android push (beyaz monochrome)   |
| `assets/favicon.png`               | 48 × 48     | Web bundle                        |

---

## Sürüm numaralandırma

- `expo.version` (`app.json`): kullanıcıya gösterilen pazarlama sürümü
  (semver, ör. `1.0.0`).
- iOS `buildNumber` ve Android `versionCode` her dağıtımda artar.
  EAS `preview` ve `production` profilleri `autoIncrement: "buildNumber"`
  / `"versionCode"` kullanır — yerel `app.json` değişikliği gerekmez.
- `runtimeVersion.policy = "appVersion"`: aynı pazarlama sürümünde OTA
  güncellemeleri uyumlu kalır.

## Bundle / paket kimlikleri

- iOS bundle identifier: `com.syroce.pms`
- Android applicationId: `com.syroce.pms`
- Expo slug: `syroce-pms-mobile`

---

## EAS kurulumu (bir kerelik)

```bash
npm install -g eas-cli
eas login
cd mobile
eas init                       # extra.eas.projectId üretir + app.json'a yazar
eas update:configure           # OTA için runtimeVersion + updates.url ekler
```

`eas init` ilk çalıştığında EAS sunucusunda yeni bir proje oluşturur ve
`app.json` → `extra.eas.projectId` alanını otomatik ekler. `eas
update:configure` OTA güncellemeleri için gerekli `updates.url` alanını
yazar; OTA kullanmayacaksanız atlayabilirsiniz. Bu iki komut tamamlanmadan
`eas build` çalıştırmayın — projeyi sunucuya bağlamak için zorunludur.

### Profiller

`eas.json` içinde üç build profili tanımlıdır:

| Profil        | Dağıtım (EAS)        | Kanal       | iOS              | Android  | Hedef                                |
| ------------- | -------------------- | ----------- | ---------------- | -------- | ------------------------------------ |
| `development` | `internal` (ad-hoc)  | development | Simulator IPA    | APK      | Expo Dev Client, yerel cihaz/sim     |
| `preview`     | `store`              | preview     | App Store imzalı | AAB      | TestFlight + Play Internal Testing   |
| `production`  | `store`              | production  | App Store imzalı | AAB      | App Store + Play production track    |

> **Not — neden `preview` da `store` dağıtımı?** EAS'te `distribution: "internal"`
> iOS için ad-hoc imzalı IPA üretir (yalnızca kayıtlı UDID'lere yüklenir) ve
> TestFlight'a yüklenemez. TestFlight (iç veya dış test) App Store sertifikasıyla
> imzalanmış store-distribution IPA ister, bu yüzden `preview.distribution`
> `"store"` olarak ayarlandı (EAS şemasında `distribution` profil seviyesinde
> yer alır, platforma özel değildir). Android tarafında dağıtım türü Play
> track seçimini etkilemez — Play Internal Testing track'i
> `submit.preview.android.track: "internal"` ile belirlenir.

`development` profili Expo Dev Client ile yerel test içindir; ad-hoc imzalama
yeterlidir. `preview` ve `production` Apple/Google store sertifikaları ile
imzalı build üretir.

---

## iOS TestFlight build

### Ön gereksinimler

- Aktif Apple Developer hesabı (Team ID, App Store Connect erişimi).
- App Store Connect'te `com.syroce.pms` bundle identifier ile uygulama
  kaydı (App ID + ASC App ID).
- `eas.json` içindeki `submit.preview.ios` alanları doldurulmuş olmalı:
  `appleId`, `ascAppId`, `appleTeamId`.

### Build

```bash
cd mobile
eas build --platform ios --profile preview
```

İlk çağrıda EAS sertifikaları (Distribution Certificate +
Provisioning Profile) sizin adınıza üretip saklamayı önerir; "Yes" deyin.
Build tamamlanınca bir IPA bağlantısı verilir.

### TestFlight'a yükleme

```bash
eas submit --platform ios --profile preview --latest
```

Komut son `preview` build'i App Store Connect'e yükler ve TestFlight'ta
"Processing" durumuna geçer. İç test grubu (Internal Testing → 100 kişiye
kadar Apple ID) anında dağıtım başlatabilir; dış test grubu Apple
incelemesinden geçer (genelde < 24 saat).

> Apple kimlik bilgileri (Apple ID parolası veya app-specific password)
> komut çalışırken etkileşimli olarak istenir. CI ortamı için
> `EXPO_APPLE_PASSWORD` ve `EXPO_APPLE_APP_SPECIFIC_PASSWORD`
> ortam değişkenlerini kullanın.

---

## Android Play Internal Testing build

### Ön gereksinimler

- Google Play Console hesabı, `com.syroce.pms` paketi ile uygulama kaydı.
- "Iç test" track'inin oluşturulmuş ve test kullanıcı listesinin tanımlı
  olması.
- Service account JSON anahtarı (`play-service-account.json`) — Play
  Console → Setup → API access üzerinden üretilir, Service Account'a
  "Release manager" rolü verilir.
- Anahtar dosyası `mobile/play-service-account.json` yoluna konur veya
  `eas.json` içindeki yol değiştirilir. **Bu dosya commit edilmemelidir
  (`.gitignore`'a eklenmiştir).**

### Build

```bash
cd mobile
eas build --platform android --profile preview
```

İlk çağrıda EAS yeni bir Android Keystore üretir ve EAS sunucularında
saklar; "Yes" deyin (üretim build'ler aynı anahtarla imzalanır).
Build tamamlanınca bir AAB (Android App Bundle) bağlantısı verilir.

### Play Internal Testing'e yükleme

```bash
eas submit --platform android --profile preview --latest
```

Komut son `preview` AAB'sini Play Console'un **internal** track'ine
"draft" durumunda yükler. Play Console'dan Review → Start rollout to
Internal testing ile yayına alınır; kayıtlı test kullanıcıları
~5 dakika içinde güncellemeyi alır.

---

## Üretim mağaza yayını (out of scope — referans)

```bash
eas build  --platform all --profile production
eas submit --platform all --profile production --latest
```

`production` profili App Store ve Play production track'ine yükler ama
inceleme tetiklemez (`releaseStatus: "draft"`). Apple App Store inceleme
için ayrıca App Store Connect'ten "Submit for Review" yapılır; Play
Console için "Send for review" düğmesine tıklanır.

---

## OTA güncelleme (yalnızca JS değişiklikleri)

Pazarlama sürümünü ve `buildNumber/versionCode`'u artırmadan, sadece
React/JS kodunda hata düzeltmesi varsa:

```bash
eas update --branch preview  --message "v1.0.0 hotfix"
eas update --branch production --message "v1.0.0 hotfix"
```

`runtimeVersion.policy = "appVersion"` olduğu için OTA, aynı pazarlama
sürümündeki tüm cihazlara dağıtılır. Native değişiklik içeren güncellemeler
mutlaka yeni bir EAS Build ister.

---

## Sürüm artırma kontrol listesi

1. `app.json` → `expo.version` semver güncelle (ör. `1.0.0` → `1.1.0`).
2. `CHANGELOG` (kök) yeni sürüm bölümünü ekle (Türkçe).
3. `eas build --profile preview` ile iç dağıtım build'ini al; iOS ve
   Android için `buildNumber` / `versionCode` otomatik artar.
4. **Smoke test** — build'i yerel iOS Simulator veya Android Emulator'a
   yükleyin, ardından `npm run smoke` ile Maestro akışlarını koşturun.
   Tüm akışlar yeşil olmadan TestFlight / Play Internal yüklemesine
   geçmeyin. Detay ve sorun giderme: [`.maestro/README.md`](.maestro/README.md).
5. `eas submit --profile preview` ile TestFlight + Play Internal'a yükle.
6. İç test (en az 24 saat, regresyon listesi) → onaylandıktan sonra
   `--profile production` ile üretim build'i ve submission. Üretim
   build'inde de `npm run smoke` adımı tekrarlanır (gerçek QA hesapları
   için `SMOKE_EMAIL` / `SMOKE_GUEST_EMAIL` env override).
7. OTA hotfix gerekiyorsa `eas update` (aynı pazarlama sürümünde).

### Smoke test akışları

`mobile/.maestro/flows/` altında dört adet Maestro akışı tanımlıdır:

| Akış                               | Doğruladığı                                          |
| ---------------------------------- | ---------------------------------------------------- |
| `login.yaml`                       | Uygulama açılır + login formu gönderilir + JWT alınır |
| `frontdesk_today.yaml`             | "Bugün" tabı yüklenir (giriş/çıkış başlıkları)        |
| `frontdesk_quick_checkin.yaml`     | Hızlı check-in ekranı açılır (QR/Kimlik tara CTA)     |
| `guest_digital_key.yaml`           | Misafir dijital anahtar ekranı render olur            |

Maestro CLI yüklü değilse `npm run smoke` net bir hata mesajıyla 127 ile
çıkar; `npm run smoke:doctor` kurulumun varlığını doğrular.

---

## Sorun giderme

| Belirti                                           | Olası neden / çözüm                                          |
| ------------------------------------------------- | ------------------------------------------------------------ |
| `eas init` "projectId already set" hatası         | `app.json` → `extra.eas.projectId` zaten dolu, atla.         |
| iOS build "missing iOS distribution certificate"  | `eas credentials` → iOS → "Set up new" ile sertifika üret.   |
| Android submit "ApiException 403"                 | Service account JSON yanlış, "Release manager" rolü eksik.   |
| TestFlight build "Invalid bundle"                 | `ITSAppUsesNonExemptEncryption` gibi `infoPlist` alanı eksik.|
| Splash ekran beyaz kalıyor                        | `app.json` → `splash.image` yolu yanlış / asset eksik.       |
| Push bildirim ikonu kare görünüyor (Android)      | `notification-icon.png` beyaz monochrome olmalı (alpha).     |
