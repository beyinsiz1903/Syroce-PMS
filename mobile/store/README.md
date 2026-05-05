# Syroce PMS — Mağaza varlıkları

Bu klasör Expo / EAS ile yapılan iç dağıtım build'leri için ihtiyaç duyulan
mağaza varlıklarını içerir. Tümü Türkçe ve Syroce kurumsal kimliğine
(lacivert + mavi vurgu) uygun şekilde üretilmiştir.

## İçerik

```
store/
├── generate_assets.py     # Tüm varlıkları yeniden üretir (PIL tabanlı, deterministik)
├── README.md              # Bu dosya
└── screenshots/
    ├── ios/
    │   ├── 01_login_6_7.png         # 1290 × 2796  (iPhone 6.7" — zorunlu)
    │   ├── 01_login_6_5.png         # 1284 × 2778  (iPhone 6.5")
    │   ├── 01_login_5_5.png         # 1242 × 2208  (iPhone 5.5" — eski cihaz)
    │   └── … (02_today, 03_quick_checkin, 04_housekeeping,
    │          05_guest_bookings, 06_digital_key)
    └── android/
        └── *_phone.png              # 1080 × 1920  (telefon)
```

## Akışlar (Türkçe başlık)

| Dosya öneki         | Akış                          | Başlık                                |
| ------------------- | ----------------------------- | ------------------------------------- |
| `01_login`          | Giriş ekranı                  | "Tek dokunuşla güvenli giriş"         |
| `02_today`          | Resepsiyon · Bugün            | "Bugünü tek bakışta yönet"            |
| `03_quick_checkin`  | Hızlı check-in (QR + kimlik)  | "30 saniyede check-in"                |
| `04_housekeeping`   | Kat hizmetleri oda listesi    | "Kat hizmetlerini canlı takip et"     |
| `05_guest_bookings` | Misafir rezervasyonlarım      | "Misafirin rezervasyonları cebinde"   |
| `06_digital_key`    | Dijital anahtar (QR + BLE)    | "Dijital anahtarla anında erişim"     |

## Yeniden üretmek

Görseller deterministiktir (rastgele tohumlar sabit). Marka renklerini
değiştirmek veya başlıkları güncellemek için `generate_assets.py` içindeki
sabitleri düzenleyin ve tekrar çalıştırın:

```bash
cd mobile
python3 store/generate_assets.py
```

Komut hem `mobile/assets/` (icon, adaptive-icon, splash, notification-icon,
favicon) hem de `mobile/store/screenshots/` altındaki tüm boyutları yeniden
oluşturur.

## App Store Connect / Play Console'a yükleme

- **iOS**: App Store Connect → Uygulamanız → "App Store" sekmesi → Türkçe
  yerelleştirmesi → "Önizlemeler ve Ekran Görüntüleri". 6.7" yuvası zorunlu;
  diğer boyutlar isteğe bağlıdır.
- **Android**: Play Console → Uygulamanız → "Mağaza profili" → Telefon
  ekran görüntüleri. 1080 × 1920 PNG'ler doğrudan yüklenebilir.
