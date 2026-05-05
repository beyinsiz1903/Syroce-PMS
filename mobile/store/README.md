# Syroce PMS — Mağaza varlıkları

Bu klasör Expo / EAS ile yapılan iç dağıtım build'leri için ihtiyaç duyulan
mağaza varlıklarını içerir. Tümü Türkçe ve Syroce kurumsal kimliğine
(lacivert + mavi vurgu) uygun şekilde üretilmiştir. Her ekran hem **koyu**
hem **light** tema varyantında, telefonun yanı sıra **iPad** ve **Android
tablet** boyutlarında üretilmektedir.

## İçerik

```
store/
├── generate_assets.py     # Tüm varlıkları yeniden üretir (PIL tabanlı, deterministik)
├── README.md              # Bu dosya
└── screenshots/
    ├── ios/
    │   ├── <flow>_6_7.png         # 1290 × 2796  iPhone 6.7" — zorunlu (koyu)
    │   ├── <flow>_6_5.png         # 1284 × 2778  iPhone 6.5"           (koyu)
    │   ├── <flow>_5_5.png         # 1242 × 2208  iPhone 5.5"           (koyu)
    │   ├── <flow>_12_9.png        # 2048 × 2732  iPad Pro 12.9"        (koyu)
    │   ├── <flow>_11.png          # 1668 × 2388  iPad Pro 11"          (koyu)
    │   └── <flow>_<size>_light.png  # aynı boyutlar için light tema
    └── android/
        ├── <flow>_phone.png            # 1080 × 1920  telefon          (koyu)
        ├── <flow>_tablet_7.png         # 1200 × 1920  tablet 7"        (koyu)
        ├── <flow>_tablet_10.png        # 1600 × 2560  tablet 10"       (koyu)
        └── <flow>_<size>_light.png     # her boyut için light tema
```

Toplamda her akış için **16 mağaza görseli** üretilir
(iOS: 5 boyut × 2 tema = 10, Android: 3 boyut × 2 tema = 6).

## Akışlar (Türkçe başlık)

| Dosya öneki         | Akış                          | Başlık                                |
| ------------------- | ----------------------------- | ------------------------------------- |
| `01_login`          | Giriş ekranı                  | "Tek dokunuşla güvenli giriş"         |
| `02_today`          | Resepsiyon · Bugün            | "Bugünü tek bakışta yönet"            |
| `03_quick_checkin`  | Hızlı check-in (QR + kimlik)  | "30 saniyede check-in"                |
| `04_housekeeping`   | Kat hizmetleri oda listesi    | "Kat hizmetlerini canlı takip et"     |
| `05_guest_bookings` | Misafir rezervasyonlarım      | "Misafirin rezervasyonları cebinde"   |
| `06_digital_key`    | Dijital anahtar (QR + BLE)    | "Dijital anahtarla anında erişim"     |

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

## Yeniden üretmek

Görseller deterministiktir (rastgele tohumlar sabit). Marka renklerini
değiştirmek, başlıkları güncellemek veya yeni boyut eklemek için
`generate_assets.py` içindeki sabitleri (`DARK`, `LIGHT`, `IOS_PHONE_SIZES`,
`IOS_TABLET_SIZES`, `ANDROID_PHONE_SIZE`, `ANDROID_TABLET_SIZES`) düzenleyin
ve tekrar çalıştırın:

```bash
cd mobile
python3 store/generate_assets.py
```

Komut hem `mobile/assets/` (icon, adaptive-icon, splash, notification-icon,
favicon) hem de `mobile/store/screenshots/` altındaki tüm boyut × tema
kombinasyonlarını yeniden oluşturur.

## App Store Connect / Play Console'a yükleme

- **iOS**: App Store Connect → Uygulamanız → "App Store" sekmesi → Türkçe
  yerelleştirmesi → "Önizlemeler ve Ekran Görüntüleri".
  - 6.7" iPhone yuvası **zorunlu**, diğer iPhone boyutları opsiyonel.
  - iPad 12.9" yuvası, App Store'da iPad'i destekleyen uygulamalar için
    **zorunlu**; 11" yuvası opsiyoneldir.
  - Tema olarak koyu varyantları yüklemek yeterlidir; light varyantları
    pazarlama materyali olarak kullanılabilir.
- **Android**: Play Console → Uygulamanız → "Mağaza profili" → Telefon
  ekran görüntüleri (1080 × 1920) **ve** "7 inç tablet" / "10 inç tablet"
  yuvaları. PNG'ler doğrudan yüklenebilir.
