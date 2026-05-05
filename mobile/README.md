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
eas login                      # Expo hesabınıza giriş yapın (yoksa: expo.dev/signup)
cd mobile
eas init                       # extra.eas.projectId üretir + app.json'a yazar
eas update:configure           # OTA için runtimeVersion + updates.url ekler
```

`eas init` ilk çalıştığında EAS sunucusunda yeni bir proje oluşturur ve
`app.json` → `extra.eas.projectId` alanını otomatik ekler (UUID formatında,
ör. `12345678-90ab-cdef-1234-567890abcdef`). `eas update:configure` OTA
güncellemeleri için gerekli `updates.url` alanını yazar; OTA
kullanmayacaksanız atlayabilirsiniz. Bu iki komut tamamlanmadan
`eas build` çalıştırmayın — projeyi sunucuya bağlamak için zorunludur.

> **Not:** `eas init` mutlaka **sizin yerel makinenizden** ve sizin
> Expo hesabınızla çalıştırılmalıdır; bu Replit container'ından
> çalıştırıldığında sizin hesabınıza bağlanamaz. Komut tamamlanınca
> `app.json` içindeki `extra.eas.projectId` değeri commit edilir, böylece
> tüm geliştiriciler ve CI aynı projeye build/submit eder.

> Mevcut bir EAS projesinin ID'sini görmek için: <https://expo.dev>
> → Projects → (proje) → Project settings → "ID" alanı.

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

- Aktif Apple Developer hesabı (yıllık $99). Henüz kaydolmadıysanız
  <https://developer.apple.com/programs/enroll/> adresinden başvurun;
  bireysel hesap onayı ~24-48 saat, kurumsal (D-U-N-S numarası gerekli)
  daha uzun sürebilir.
- App Store Connect'te `com.syroce.pms` bundle identifier ile uygulama
  kaydı (App ID + ASC App ID).
- `eas.json` içindeki `submit.preview.ios` ve `submit.production.ios`
  alanları doldurulmuş olmalı: `appleId`, `ascAppId`, `appleTeamId`.

### `eas.json` için gerekli değerleri nereden bulurum?

| Alan          | Nerede bulunur                                                                       | Örnek format                |
| ------------- | ------------------------------------------------------------------------------------ | --------------------------- |
| `appleId`     | App Store Connect'e giriş yaptığınız e-posta. <https://appstoreconnect.apple.com>     | `you@example.com`           |
| `appleTeamId` | <https://developer.apple.com/account> → "Membership details" → "Team ID" alanı.       | 10 karakter, ör. `A1B2C3D4E5` |
| `ascAppId`    | <https://appstoreconnect.apple.com> → My Apps → (uygulamanız) → App Information → "Apple ID" satırı (sayısal değer, "Bundle ID" değil). | Sayısal, ör. `1234567890`   |

> ⚠ **Apple ID parolanızı asla `eas.json`'a yazmayın veya kimseyle
> paylaşmayın.** `eas.json` git'e commit edilir; yalnızca e-posta + ID
> değerleri içerir. Parola `eas submit` çalışırken interaktif olarak
> sorulur (veya `EXPO_APPLE_PASSWORD` ortam değişkeninden okunur).

### Apple kayıt akışı (ASC App ID üretmek için)

1. Apple Developer Program'a kayıt olun ve onaylanmasını bekleyin.
2. <https://developer.apple.com/account/resources/identifiers/list>
   sayfasında "+" → App IDs → App ile yeni bir bundle ID oluşturun:
   `com.syroce.pms`. Capabilities olarak Push Notifications'ı işaretleyin.
3. <https://appstoreconnect.apple.com> → My Apps → "+" → New App ile
   uygulamayı oluşturun (platform: iOS, bundle ID: `com.syroce.pms`,
   SKU serbest seçilebilir, ör. `syroce-pms-001`).
4. Oluşturulan uygulamanın "App Information" sayfasında **Apple ID**
   alanı (sayısal) artık görünür — bu değer `eas.json` içindeki
   `ascAppId` alanına yazılır.

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

- Google Play Console hesabı (tek seferlik $25 kayıt ücreti).
  Henüz kaydolmadıysanız <https://play.google.com/console/signup>.
- `com.syroce.pms` paketi ile Play Console'da uygulama kaydı.
- "Iç test" track'inin oluşturulmuş ve test kullanıcı listesinin tanımlı
  olması.
- Service account JSON anahtarı (`play-service-account.json`).
- Anahtar dosyası `mobile/play-service-account.json` yoluna konur veya
  `eas.json` içindeki yol değiştirilir. **Bu dosya commit edilmemelidir
  (`.gitignore`'a eklenmiştir).**

### `play-service-account.json` nasıl üretilir?

1. Play Console → Setup → **API access** sayfasını açın.
2. Eğer henüz bağlı bir Google Cloud projesi yoksa "Link Google Cloud
   project" → yeni proje oluşturun veya mevcut bir projeyi seçin.
3. "Service accounts" bölümünde **Create new service account** →
   açılan link sizi Google Cloud Console'a götürür.
4. Google Cloud Console → IAM & Admin → Service Accounts → "+ CREATE
   SERVICE ACCOUNT". İsim serbest, ör. `eas-publisher`.
5. Oluşturulan service account satırında ⋮ menüsü → **Manage keys** →
   **Add key** → **Create new key** → JSON formatı seçin. Dosya otomatik
   olarak indirilir (`<proje>-<rastgele>.json`).
6. Bu dosyayı `mobile/play-service-account.json` adıyla **mobile**
   klasörüne kopyalayın (rename gerekirse).
7. Play Console → API access sayfasına dönün, yeni service account
   listede görünmeli. **Grant access** → izin olarak en az
   "Release manager" (veya "Admin") seçin → **Invite user** → **Send
   invitation**.

> ⚠ `play-service-account.json` hassas bir kimlik bilgisidir; Google
> Play hesabınıza yazma erişimi verir. Asla commit etmeyin, asla
> başkasıyla paylaşmayın. `.gitignore`'a zaten eklenmiş durumda.

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
4. **Smoke test (CI üzerinden zorunlu)** — Build başarıyla bittiğinde
   GitHub Actions'taki `Mobile Smoke (post EAS build)` iş akışı otomatik
   ya da manuel olarak tetiklenir; build artifact'i indirilir, iOS
   Simulator / Android Emulator'a kurulur ve `mobile/scripts/smoke.sh`
   çalıştırılır. Bu akış olmadan **`eas submit` adımına geçmeyin** —
   `Smoke gate` job'u kırmızıysa sürüm bloklanmıştır. Akış nasıl
   tetiklenir, otomatik webhook bağlanır ve sonuçlar PR'a yorumlanır:
   [Otomatik smoke CI hook'u](#otomatik-smoke-ci-hooku). Yerel akış
   detayı: [`.maestro/README.md`](.maestro/README.md).
5. CI smoke yeşil olduktan sonra `eas submit --profile preview` ile
   TestFlight + Play Internal'a yükle.
6. İç test (en az 24 saat, regresyon listesi) → onaylandıktan sonra
   `--profile production` ile üretim build'i ve submission. Üretim
   build'inde de aynı CI smoke akışı tekrar çalıştırılır (`profile:
   production` girdisi ile); gerçek QA hesapları için repo secret'ları
   `SMOKE_EMAIL` / `SMOKE_PASSWORD` / `SMOKE_GUEST_EMAIL` /
   `SMOKE_GUEST_PASSWORD` doldurulmuş olmalı.
7. OTA hotfix gerekiyorsa `eas update` (aynı pazarlama sürümünde).

> **Smoke başarısız olursa:** `eas submit` koşturulmaz. Hatanın kaynağı
> Maestro çıktı log'undan (Actions run → `maestro-ios-debug` /
> `maestro-android-debug` artifact'ı) tespit edilir, düzeltme kodda ya da
> akışta yapılır, yeni bir EAS build alınır ve smoke tekrarlanır. Bu
> kontrol "manuel onay" değil, dağıtımdan önce zorunlu otomatik kapıdır.

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

## Otomatik smoke CI hook'u

`.github/workflows/mobile-smoke.yml` iş akışı, EAS build artifact'ını alıp
GitHub Actions runner'ları üzerinde Maestro smoke akışlarını otomatik
koşturur. Varsayılan koşum GitHub-hosted runner'lardadır (`macos-14` iOS
için, `ubuntu-latest` Android için); self-hosted runner kullanmak
isteyenler aynı etiketleri kendi makinelerine atayıp `runs-on` satırını
değiştirebilir. `eas submit` adımına geçilebilmesi için bu akışın yeşil
olması zorunludur — `Smoke gate` job'u branch protection'da "required
check" olarak ayarlanmalıdır.

### Tetikleyiciler

1. **Manuel (`workflow_dispatch`)** — Actions sekmesinden:
   - `platform`: `ios`, `android` veya `both`
   - `build_url`: EAS build sayfasındaki artifact URL'si (iOS için
     `*.tar.gz` simulator build, Android için APK; AAB ve App Store
     imzalı IPA simülatöre/emülatöre doğrudan kurulamaz, ayrıntı için
     `eas.json` profillerine bakın)
   - `profile`: `preview` veya `production` (sadece raporlama)
   - `issue_number`: opsiyonel — sonuçların yorumlanacağı PR / issue.

2. **Otomatik (`repository_dispatch`, `eas-build-finished`)** — EAS
   webhook'u doğrudan GitHub Actions'ı tetikleyemez; arada küçük bir
   röle servisi konur. Röle servisinin kodu, K8s manifesti, Dockerfile'ı
   ve operasyonel runbook'u repo içinde:
   [`infra/eas-webhook-relay/`](../infra/eas-webhook-relay/README.md).

   ```text
   EAS build webhook  ──HMAC-SHA1──▶  röle (infra/eas-webhook-relay)
                                         │
                                         ▼
                       POST /repos/<owner>/<repo>/dispatches
                       { event_type: "eas-build-finished",
                         client_payload: { platform, build_url,
                                           build_id, profile,
                                           issue_number? } }
   ```

   Röle:
   - `expo-signature` başlığını `EAS_WEBHOOK_SECRET` ile HMAC-SHA1
     doğrular (sabit zamanlı karşılaştırma),
   - `status != "finished"` olan webhook'ları yutar (in-queue,
     in-progress, errored, canceled — hiçbiri smoke tetiklemez),
   - `payload.artifacts.applicationArchiveUrl`, `payload.id`,
     `payload.platform` ve `payload.metadata.buildProfile` alanlarını
     yukarıdaki `client_payload` şemasına çevirip GitHub API'ye gönderir
     (PAT veya GitHub App installation token, `repo` scope).
   - `issue_number` opsiyoneldir; commit mesajı / branch adı içinde
     `PR-<n>`, `#<n>` veya `pr-<n>/...` deseni varsa otomatik çıkarılır,
     yoksa atlanır ve workflow yorum adımını sessizce atlar.

   **Üretim deploy URL'si:** `https://eas-relay.syroce.com/eas`
   (ingress + cert-manager üzerinden; healthcheck `/health`).

   Webhook'u kurmak için:

   ```bash
   export EAS_WEBHOOK_SECRET=$(openssl rand -hex 32)
   eas webhook:create \
     --event BUILD \
     --url https://eas-relay.syroce.com/eas \
     --secret "$EAS_WEBHOOK_SECRET"
   # Aynı secret röleye `EAS_WEBHOOK_SECRET` env değişkeni olarak verilir
   # (k8s: secret/eas-webhook-relay-secrets, bkz. infra/eas-webhook-relay/k8s/deployment.yml).
   ```

   Token / secret rotasyonu, gözden geçirme ve "build bitti ama smoke
   çalışmadı" runbook'u için
   [`infra/eas-webhook-relay/README.md`](../infra/eas-webhook-relay/README.md#operations-runbook).

### Runner gereksinimleri

- **iOS** → `macos-14` runner kullanılır; GitHub-hosted macOS runner'ları
  üzerinde Xcode + iOS Simulator hazır gelir. Self-hosted bir Mac mini
  tercih edilirse aynı etiketle eklenip `runs-on` değiştirilebilir.
- **Android** → `ubuntu-latest` üzerinde
  [`reactivecircus/android-emulator-runner`](https://github.com/ReactiveCircus/android-emulator-runner)
  ile API 34 / `pixel_6` AVD koşulur. KVM hardware accel etkinleştirilir.
  BrowserStack / Sauce Labs entegrasyonu gerekirse aynı job içinde
  `app_url` ile değiştirilebilir.

### Repo secret'ları (zorunlu — gerçek QA hesapları)

| Secret                  | Açıklama                                         |
| ----------------------- | ------------------------------------------------ |
| `SMOKE_EMAIL`           | Resepsiyon QA hesabı e-postası                   |
| `SMOKE_PASSWORD`        | Resepsiyon QA hesabı şifresi                     |
| `SMOKE_GUEST_EMAIL`     | Misafir QA hesabı e-postası                      |
| `SMOKE_GUEST_PASSWORD`  | Misafir QA hesabı şifresi                        |

Doldurulmazsa flow'lar `mobile/.maestro/flows/login.yaml` içindeki demo
varsayılanlarına düşer; üretim build'i için bu **kabul edilemez**.

### Çıktılar

- `GITHUB_STEP_SUMMARY` → her platform için "Sonuc / Build URL / Cihaz"
  özeti + Maestro çıktısının son 80 satırı.
- Workflow artifact'ları: `maestro-ios-debug`, `maestro-android-debug`
  (tam log + `~/.maestro/tests` içindeki ekran görüntüleri).
- `issue_number` verildiyse PR / issue'ya tek bir özet yorum atılır.
- `Smoke gate` job'u — istenen tüm platformlar geçmediyse `exit 1`.
  Bu tek check'i branch protection'a "required" eklemek `eas submit`'i
  fiilen kilitler.

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
