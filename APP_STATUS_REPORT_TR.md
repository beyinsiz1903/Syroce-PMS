# Syroce PMS – Uygulama Durum Raporu (Preview)

> Tarih: 2025-12-18
> 
> Ortamlar:
> - Preview: https://hotel-pms-demo.preview.emergentagent.com
> - Canlı: https://syroce.com
> 
> Önemli not: Preview ve canlı **farklı veritabanları** kullanabilir. Bu yüzden canlıda giriş yapan kullanıcılar preview’da 401 alabilir.

---

## 1) Genel Durum Özeti

### ✅ Çalışan ana modüller
- Kimlik doğrulama (login)
- Tenant / otel yönetimi
- PMS (Rooms, Bookings, Guests vb.) ekranı
- Reservation Calendar (Enterprise/AI/Deluxe panelleri + boş veri uyarıları)

### ✅ Son eklenen / iyileştirilen kritik özellikler
1) **Üyelik sürelerini manuel tarih ile güncelleme** (start/end date)
2) Reservation Calendar’da **veri yokken yanıltıcı metrikleri gizleme**
3) PMS Rooms:
   - **Bulk oda oluşturma** (Range + Template)
   - **CSV import** ile toplu oda ekleme
   - Oda meta alanları: **view (manzara), bed_type, amenities, images**
   - **Oda fotoğraf yükleme** (sunucuya; MVP)
   - Rooms listesinde filtreler: **room_type / view / amenity**
4) **Toplu oda silme (soft delete)** + yanlışlıkla silmeye karşı korumalar
5) PMS loadData: `Promise.allSettled` ile **kısmi hata toleransı** (örn. bir endpoint 403 verirse sayfa çökmez)
6) Header’da **otel adının uzun olması**: truncate + tooltip + mobilde görünür hale getirildi

---

## 2) Ortam ve Veri Davranışı

### Preview vs Canlı
- Preview ve canlı farklı MongoDB/DB_NAME kullanıyorsa kullanıcılar ortamlar arasında taşınmaz.
- "Canlıda giriş yapabiliyorum ama preview’da hata" → tipik sebep: preview DB’de o kullanıcı yok.

### Redeploy verileri siler mi?
- Normalde **hayır**: Kullanıcılar/odalar/rezervasyonlar MongoDB’de durur.
- Ancak **dosya yüklemeleri** (oda fotoğrafları) sunucu diskinde ise, prod ortamın diski kalıcı değilse redeploy sonrası dosyalar kaybolabilir.

---

## 3) Backend (FastAPI) – API Özeti (Önemli Endpoint’ler)

> Tüm backend route’ları `/api` prefix’i ile çalışır (ingress kuralı).

### 3.1 Auth
- `POST /api/auth/login`
- `GET /api/auth/me`

### 3.2 Tenant Subscription (Super Admin)
- `PATCH /api/admin/tenants/{tenant_id}/subscription`

Payload (manuel tarih destekli):
```json
{
  "subscription_days": 30,
  "subscription_start_date": "2025-01-05",
  "subscription_end_date": "2025-03-10"
}
```
- `subscription_start_date` / `subscription_end_date` doluysa backend bu tarihleri **tercih eder**.
- `subscription_end_date` boş/"" ise: **Sınırsız**

### 3.3 Rooms
#### Tek oda
- `POST /api/pms/rooms`
- `GET /api/pms/rooms?limit=...&room_type=...&view=...&amenity=...`

Room alanları (özet):
- `room_number` (string, prefix destekli)
- `room_type`
- `floor`, `capacity`, `base_price`
- `amenities[]`
- `view`, `bed_type`
- `images[]`
- **Soft delete**: `is_active`, `deleted_at`

#### Bulk create
- `POST /api/pms/rooms/bulk/range`
```json
{
  "prefix": "A",
  "start_number": 101,
  "end_number": 200,
  "floor": 1,
  "room_type": "deluxe",
  "capacity": 2,
  "base_price": 150,
  "amenities": ["wifi"],
  "view": "sea",
  "bed_type": "king"
}
```

- `POST /api/pms/rooms/bulk/template`
```json
{
  "prefix": "B",
  "start_number": 1,
  "count": 10,
  "floor": 2,
  "room_type": "standard",
  "capacity": 2,
  "base_price": 90
}
```

#### CSV import
- `POST /api/pms/rooms/import-csv` (multipart form-data, field: `file`)

CSV kolonları:
- `room_number, room_type, floor, capacity, base_price, view, bed_type, amenities`
- amenities formatı: `wifi|balcony|minibar`
- Limit: max 2000 satır, max 2MB

#### Fotoğraf yükleme
- `POST /api/pms/rooms/{room_id}/images` (multipart, field: `files` çoklu)
- Statik servis: `/api/uploads/...`

#### Bulk delete (soft delete)
- `POST /api/pms/rooms/bulk/delete`

Payload örnek (seçili odalarla):
```json
{
  "ids": ["room_uuid_1", "room_uuid_2"],
  "confirm_text": "DELETE"
}
```

Güvenlik:
- Yetki: `admin + super_admin`
- Onay: `confirm_text` → `DELETE` (case-insensitive)
- Koruma: `confirmed/checked_in` booking’i olan odalar **bloklanır**

---

## 4) Frontend (React) – UI Özeti

### 4.1 PMS → Rooms
- “Hızlı / Çoklu Oda Ekle” modalı
  - Range
  - Template
  - CSV Import (aktif)
- Bulk Mode
  - Çoklu seçim checkbox
  - Toplu silme modalı (DELETE yazmadan sil butonu aktif olmaz)
- Oda kartında meta rozetleri:
  - view, bed_type, amenities
- Oda fotoğrafları:
  - “Fotoğraflar” butonu → galeri + upload

### 4.2 Reservation Calendar
- Enterprise / AI / Deluxe panellerinde:
  - Eğer oda yoksa veya tarih aralığında booking yoksa: **Türkçe uyarı + metrik gizleme**

### 4.3 Header (Layout)
- Otel adı artık mobilde de görünür.
- Uzun isimler: `truncate` + `title` (tooltip)

---

## 5) Test Durumu (Özet)

- Backend: 
  - Auth login/me ✅
  - Subscription manual date patch ✅
  - Bulk create range/template ✅
  - CSV import ✅
  - Bulk delete ✅
  - Rooms is_active filtre backward compatible ✅

- Frontend:
  - Bulk delete UI Playwright testi ✅
  - Reservation Calendar empty-dataset mesajları ✅

---

## 6) Bilinen Limitler / Riskler

1) **Fotoğraflar sunucu diskine yükleniyor**: prod’da disk kalıcı değilse redeploy sonrası kaybolabilir.
   - Çözüm: S3/Cloudinary gibi kalıcı storage entegrasyonu.
2) `test_result.md` içinde geçmişten kalan bazı minor eslint/ruff uyarıları olabilir; kritik çalışmayı engelleyen bir durum görünmüyor.
3) Preview ve canlı DB farkı: canlı kullanıcılarının preview’da görünmemesi normal.

---

## 7) Önerilen Sıradaki İyileştirmeler

- (Öneri) “Silinen odalar” filtresi + “Geri Al (restore)” butonu
- (Öneri) Oda fotoğrafları için kalıcı storage (S3/Cloudinary)
- (Öneri) Rezervasyon oluştururken oda filtreleme (room_type/view/amenity) – istenirse UI üzerinde genişletme
- (Öneri) Audit log görünürlüğü/filtreleri ve log içeriği maskeleme

---

## 8) Kullanıcılar / Roller

- Audit logs: **admin + super_admin** erişebilir (403 sorunu giderildi).
- Bulk delete: **admin + super_admin**

---

### Dosya Konumu
Bu rapor: `/app/APP_STATUS_REPORT_TR.md`
