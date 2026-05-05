# Syroce PMS — Mağaza varlıkları

Bu klasör Expo / EAS ile yapılan iç dağıtım build'leri için ihtiyaç duyulan
mağaza varlıklarını içerir. Tümü Syroce kurumsal kimliğine
(lacivert + mavi vurgu) uygun şekilde üretilmiştir. Her ekran hem **koyu**
hem **light** tema varyantında, telefonun yanı sıra **iPad** ve **Android
tablet** boyutlarında üretilmektedir. Varsayılan dil Türkçedir; ek olarak
App Store / Play Store global liste için **İngilizce yerelleştirme** de
üretilir ve `ios/en/` ile `android/en/` altına yazılır.

## İçerik

```
store/
├── generate_assets.py     # Statik ekran görüntüleri + ikonlar (PIL, deterministik)
├── generate_videos.py     # 15-30 sn'lik mağaza tanıtım videoları (PIL + ffmpeg)
├── README.md              # Bu dosya
└── screenshots/
    ├── ios/                            # Türkçe (varsayılan)
    │   ├── <flow>_6_7.png         # 1290 × 2796  iPhone 6.7" — zorunlu (koyu)
    │   ├── <flow>_6_5.png         # 1284 × 2778  iPhone 6.5"           (koyu)
    │   ├── <flow>_5_5.png         # 1242 × 2208  iPhone 5.5"           (koyu)
    │   ├── <flow>_12_9.png        # 2048 × 2732  iPad Pro 12.9"        (koyu)
    │   ├── <flow>_11.png          # 1668 × 2388  iPad Pro 11"          (koyu)
    │   ├── <flow>_<size>_light.png  # aynı boyutlar için light tema
    │   └── en/                          # İngilizce yerelleştirme (aynı boyutlar)
    │       └── <flow>_<size>[_light].png
    └── android/                        # Türkçe (varsayılan)
        ├── <flow>_phone.png            # 1080 × 1920  telefon          (koyu)
        ├── <flow>_tablet_7.png         # 1200 × 1920  tablet 7"        (koyu)
        ├── <flow>_tablet_10.png        # 1600 × 2560  tablet 10"       (koyu)
        ├── <flow>_<size>_light.png     # her boyut için light tema
        └── en/                          # İngilizce yerelleştirme (aynı boyutlar)
            └── <flow>_<size>[_light].png
├── videos/
    ├── ios/
    │   ├── <flow>_6_7.mp4         # 1080 × 1920   iPhone 6.7" preview (App Store)
    │   └── <flow>_12_9.mp4        # 1200 × 1600   iPad Pro 12.9" preview
    └── android/
        ├── <flow>_phone.mp4       # 1080 × 1920   telefon (Play / YouTube 9:16)
        └── <flow>_tablet_10.mp4   # 1200 × 1920   10" tablet
```

Toplamda her akış için her dilde **16 mağaza görseli + 4 tanıtım videosu** üretilir
(iOS: 5 boyut × 2 tema = 10, Android: 3 boyut × 2 tema = 6 görsel; 4 video boyutu). İki dil için
toplam **32 görsel/akış**, 6 akışta **192 mağaza görseli** üretilir.

## Akışlar ve başlıklar

| Dosya öneki         | Akış                          | Türkçe başlık                         | İngilizce başlık                          |
| ------------------- | ----------------------------- | ------------------------------------- | ----------------------------------------- |
| `01_login`          | Giriş ekranı                  | "Tek dokunuşla güvenli giriş"         | "Secure sign-in with one tap"             |
| `02_today`          | Resepsiyon · Bugün            | "Bugünü tek bakışta yönet"            | "Manage today at a glance"                |
| `03_quick_checkin`  | Hızlı check-in (QR + kimlik)  | "30 saniyede check-in"                | "Check in in 30 seconds"                  |
| `04_housekeeping`   | Kat hizmetleri oda listesi    | "Kat hizmetlerini canlı takip et"     | "Track housekeeping in real time"         |
| `05_guest_bookings` | Misafir rezervasyonlarım      | "Misafirin rezervasyonları cebinde"   | "Guest bookings in your pocket"           |
| `06_digital_key`    | Dijital anahtar (QR + BLE)    | "Dijital anahtarla anında erişim"     | "Instant access with the digital key"     |

## Boyut tablosu

### iOS (App Store Connect)

| Anahtar | Çözünürlük   | Cihaz                       | Çerçeve  |
| ------- | ------------ | --------------------------- | -------- |
| `6_7`   | 1290 × 2796  | iPhone 6.7" (zorunlu)       | telefon  |
| `6_5`   | 1284 × 2778  | iPhone 6.5"                 | telefon  |
| `5_5`   | 1242 × 2208  | iPhone 5.5" (eski cihaz)    | telefon  |
| `12_9`  | 2048 × 2732  | iPad Pro 12.9" (3. nesil+)  | tablet   |
| `11`    | 1668 × 2388  | iPad Pro 11" / iPad Air     | tablet   |

### Android (Google Play Console)

| Anahtar      | Çözünürlük   | Hedef                       | Çerçeve  |
| ------------ | ------------ | --------------------------- | -------- |
| `phone`      | 1080 × 1920  | Telefon                     | telefon  |
| `tablet_7`   | 1200 × 1920  | 7" tablet                   | tablet   |
| `tablet_10`  | 1600 × 2560  | 10" tablet                  | tablet   |

## Tema varyantları

- **Koyu (varsayılan)**: lacivert (`#0b0f1a`) zemin, açık metin. Dosya adında
  ek sonek yoktur (örn. `02_today_6_7.png`).
- **Light**: nötr açık (`#f7f8fb`) zemin, koyu metin. `_light` sonekiyle
  ayrılır (örn. `02_today_6_7_light.png`). Pazarlama gücünü artırmak ve light
  şemayı tercih eden kullanıcılara doğru görsel beklenti vermek için ek olarak
  üretilir; mağazaya yüklemek opsiyoneldir.

## Yerelleştirme

Tüm ekran içi metinler ve mağaza başlıkları `generate_assets.py` içindeki
`COPY_TR` ve `COPY_EN` sözlüklerinde sabit anahtarlar altında tutulur. Yeni
bir dil eklemek için aynı anahtarlarla `COPY_<lang>` sözlüğü oluşturup
`LOCALES` listesine `Locale(code="<lang>", out_subdir="<lang>", copy=...)`
eklemek yeterlidir. Türkçe varsayılan kabul edildiği için `out_subdir=""`
ile mevcut yola yazılır; diğer diller `ios/<lang>/` ve `android/<lang>/`
altına yazılır.

## Tanıtım videoları (App Preview / Promo Video)

Statik ekran görüntülerinin yanı sıra, App Store Connect ve Google Play her
cihaz boyutu için kısa **tanıtım videosu** da kabul eder. Bu videolar
tıklama oranını ve mağaza dönüşümünü ciddi şekilde artırır.

`generate_videos.py` her akış için **18 saniyelik** (App Store'un 15-30 sn
aralığında), animasyonlu, sessiz **H.264 MP4** çıktıları üretir. Her video şu
fazlardan oluşur:

1. **Intro (0 – 2.5 sn)** — Türkçe başlık ve vurgu çubuğu fade-in,
   cihaz aşağıdan yukarı süzülerek yerleşir.
2. **Showcase (3 – 15 sn)** — Cihaz ekranı boyunca aşağıya inen, marka mavisi
   yumuşak bir spotlight bandı dolaşır (2 döngü) — kullanıcının dikkatini
   ekran içeriğinde gezdirir.
3. **Outro (15.5 – 18 sn)** — Aşağıdan yukarı süzülen "App Store ve Google
   Play'de" CTA rozeti.

### Video boyutları

| Dosya                       | Çözünürlük   | Hedef yuva                         |
| --------------------------- | ------------ | ---------------------------------- |
| `ios/<flow>_6_7.mp4`        | 1080 × 1920  | App Store — iPhone 6.7" App Preview |
| `ios/<flow>_12_9.mp4`       | 1200 × 1600  | App Store — iPad Pro 12.9" App Preview |
| `android/<flow>_phone.mp4`  | 1080 × 1920  | Play / YouTube — telefon (9:16)     |
| `android/<flow>_tablet_10.mp4` | 1200 × 1920 | Play / YouTube — 10" tablet         |

Her video ~600 KB – 1.2 MB arası, libx264 + yuv420p + `+faststart`
(iOS uyumlu) ile kodlanmıştır. Sessizdir: App Store sessiz preview kabul
eder, Play Store ise zaten doğrudan MP4 değil YouTube linki bekler.

## Yeniden üretmek

Görseller ve videolar deterministiktir (rastgele tohumlar sabit). Marka
renklerini değiştirmek, başlıkları güncellemek, yeni dil veya yeni boyut eklemek için
`generate_assets.py` içindeki sabitleri (`DARK`, `LIGHT`, `COPY_TR`,
`COPY_EN`, `LOCALES`, `IOS_PHONE_SIZES`, `IOS_TABLET_SIZES`,
`ANDROID_PHONE_SIZE`, `ANDROID_TABLET_SIZES`) düzenleyin
ve tekrar çalıştırın:

```bash
cd mobile
python3 store/generate_assets.py     # ikon + ekran görüntüleri
python3 store/generate_videos.py     # mağaza tanıtım videoları (24 MP4 ~ 7 dk)
```

`generate_assets.py` hem `mobile/assets/` (icon, adaptive-icon, splash,
notification-icon, favicon) hem de `mobile/store/screenshots/` altındaki tüm
boyut × tema kombinasyonlarını yeniden oluşturur.

`generate_videos.py` aynı `screen_*` fonksiyonlarını yeniden kullanır;
her akışı tek seferde render edip animasyon katmanını her kare için yeniden
çizer ve ffmpeg pipe üzerinden MP4'e kodlar. Faydalı bayraklar:

```bash
python3 store/generate_videos.py --flow 02_today    # tek akış (4 video)
python3 store/generate_videos.py --light            # light tema da üret
python3 store/generate_videos.py --smoke            # küçük test (540×960, 6 sn)
```

Bağımlılıklar: Pillow (zaten gerekiyor) ve `ffmpeg` (libx264).

> Komutun yalnızca standart kütüphane + **Pillow 12.1.1** ve sistem
> üzerinde **DejaVu Sans / DejaVu Sans Bold** yazı tiplerinin kurulu
> olmasına ihtiyacı vardır. Ubuntu üzerinde:
> `sudo apt-get install fonts-dejavu-core && pip install Pillow==12.1.1`.

## CI sürüklenme guard'ı

`.github/workflows/mobile-store-assets.yml` her PR'da (yalnızca
`mobile/store/generate_assets.py`, `mobile/store/screenshots/**` veya
`mobile/assets/**` değiştiğinde) jeneratörü yeniden çalıştırır ve
çıktıyı commit'li PNG'lerle karşılaştırır. Çıktı deterministik
olduğundan herhangi bir fark olması demek, geliştiricinin bir
pazarlama görselini etkileyen kod değişikliği yapıp scripti
çalıştırmayı unuttuğu anlamına gelir; bu durumda iş başarısız olur ve
"Summary" sekmesinde değişen dosyalar listelenir. Düzeltmek için:

```bash
cd mobile
python3 store/generate_assets.py
git add mobile/store/screenshots mobile/assets
```

İşlem başarısız olursa CI ayrıca **`regenerated-store-assets`** adında
bir artifact yükler — bunu indirip içeriğini repo üzerine kopyalayıp
commit ederek de düzeltebilirsiniz.

## App Store Connect / Play Console'a yükleme

- **iOS — Ekran görüntüleri**: App Store Connect → Uygulamanız → "App Store"
  sekmesi → Türkçe yerelleştirmesi → "Önizlemeler ve Ekran Görüntüleri".
  - Türkçe yerelleştirme için `screenshots/ios/` altındaki PNG'leri,
    İngilizce (English U.S./U.K.) yerelleştirme için `screenshots/ios/en/`
    altındaki PNG'leri yükleyin.
  - 6.7" iPhone yuvası **zorunlu**, diğer iPhone boyutları opsiyonel.
  - iPad 12.9" yuvası, App Store'da iPad'i destekleyen uygulamalar için
    **zorunlu**; 11" yuvası opsiyoneldir.
  - Tema olarak koyu varyantları yüklemek yeterlidir; light varyantları
    pazarlama materyali olarak kullanılabilir.
- **iOS — App Previews (videolar)**: Aynı ekranda her boyut yuvasının
  üst kısmındaki "App Previews" alanına en fazla 3 video yüklenebilir.
  - `mobile/store/videos/ios/<flow>_6_7.mp4` → iPhone 6.7" yuvası
  - `mobile/store/videos/ios/<flow>_12_9.mp4` → iPad Pro 12.9" yuvası
  - Her preview 15-30 sn arası olmalı (videolarımız 18 sn'dir).
- **Android**: Play Console → Uygulamanız → "Mağaza profili" → Telefon
  ekran görüntüleri (1080 × 1920) **ve** "7 inç tablet" / "10 inç tablet"
  yuvaları. Türkçe varsayılan listeleme için `screenshots/android/`,
  İngilizce ek listeleme için `screenshots/android/en/` altındaki PNG'ler
  doğrudan yüklenebilir.
- **Android — Tanıtım videosu**: Play Console "Tanıtım videosu" alanı
  yalnızca **YouTube linki** kabul eder, doğrudan MP4 yüklenmez. Önerilen
  akış: `videos/android/<flow>_phone.mp4` (veya `_tablet_10`) dosyasını
  pazarlama hesabınızdan YouTube'a yükleyin (gizli/genel) ve linki Play
  Console'a yapıştırın. Aynı dosyalar Instagram Reels / TikTok / LinkedIn
  reklamlarında doğrudan kullanılabilir.
