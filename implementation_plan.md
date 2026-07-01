# Pilot Demo Flow / Core PMS Smoke Test Plan

## Hedef
Syroce PMS'in pilot otel demosunda gösterilecek olan 13 adımlık ana operasyon akışını (Demo Flow) uçtan uca doğrulamak için bir "Smoke Test Script" oluşturmak ve kırılan endpoint'leri izole olarak onarmak.

## User Review Required
> [!IMPORTANT]
> Bu plan, sandbox ortamımızda gerçek MongoDB ve Docker bulunmaması kısıtlamasını aşmak için **iki katmanlı bir yaklaşım** önermektedir.
> Ben (Antigravity), uçtan uca API çağrılarını yapan `smoke_demo_flow.py` scriptini hazırlayacağım. Testi gerçek bir staging veya local veritabanı ile tetiklemek senin ortamında gerçekleşecek. Ben ise önceden kod bazında bu endpoint'leri "Statik Audit" ile tarayarak bariz import/mantık hatalarını tespit edeceğim.

## 13 Adımlı Demo Akışı ve Hedef Endpoint Eşleştirmeleri

| Adım | İşlem | Beklenen Endpoint / Frontend Sayfası |
|---|---|---|
| 1 | Login (Dashboard'da kalır) | `POST /api/auth/login` ➔ `AuthPage.jsx` |
| 2 | Dashboard temel verileri | `GET /api/rms/dashboard-kpis` veya `GET /api/pms/dashboard/overview` ➔ `Dashboard.jsx` |
| 3 | Arrival list (Bugün girişler) | `GET /api/pms/bookings` (status=arrival) ➔ `ArrivalList.jsx` |
| 4 | Yeni rezervasyon oluştur | `POST /api/pms/bookings` ➔ `ReservationCalendar.jsx` |
| 5 | Rezervasyon detayı | `GET /api/pms/bookings/{id}` ➔ `ReservationDetailModal.jsx` |
| 6 | Check-in yap | `POST /api/pms/bookings/{id}/check-in` |
| 7 | Oda durumunu değiştir | `POST /api/housekeeping/rooms/{id}/status` ➔ `HousekeepingDashboard.jsx` |
| 8 | Folio'ya charge ekle | `POST /api/folio/{folio_id}/charges` ➔ `FolioDetailView.jsx` |
| 9 | Payment (Ödeme) al | `POST /api/folio/{folio_id}/payments` ➔ `FolioDetailView.jsx` |
| 10 | Room move / Upgrade | `POST /api/pms/bookings/{id}/room-move` |
| 11 | Housekeeping task oluştur | `POST /api/housekeeping/tasks` |
| 12 | Check-out yap | `POST /api/pms/bookings/{id}/check-out` |
| 13 | Night audit status | `GET /api/pms/night_audit/status` ➔ `NightAuditDashboard.jsx` |

## Önerilen Değişiklikler ve Aksiyon Planı

### 1. `smoke_demo_flow.py` Scriptinin Oluşturulması
`backend/scripts/smoke_demo_flow.py` adında bağımsız bir betik yazılacaktır. Bu betik:
- Verilen bir `--base-url` üzerinden çalışacak.
- Başarılı olan adımları yeşil, API 500 dönen veya timeout olan adımları kırmızı yazdıracak.
- Senin lokalinde `python scripts/smoke_demo_flow.py --base-url http://localhost:8000` komutuyla 30 saniyede tüm demo akışının röntgenini çekecek.

### 2. Statik Kod Denetimi ve Kırık Uçların Tespiti
Sen testi çalıştırmadan önce ben, yukarıdaki 13 endpointin ilgili `router.py` dosyalarını okuyarak:
- NameError veya ImportError var mı?
- Eksik veritabanı (db) proxy bağlantısı var mı?
- Tip uyuşmazlığı (Pydantic validation error riski) var mı? 
kontrollerini yapacağım ve kırık olanlar için ayrı `fix-demo-flow-[modül]` branch'leri oluşturacağım.

### 3. APM Middleware ve Diğer Teknik Borçlar
- `apm_middleware` hatası ve `fix-slow-api-endpoints` branch'i teknik borç backlog'unda tutulacak. Main'e doğrudan merge yapılmayacaktır.

## Verification Plan
1. **Benim Doğrulamam:** `smoke_demo_flow.py` dosyasının başarıyla oluşturulması ve syntax hatası içermemesi.
2. **Senin Doğrulaman (Live):** Staging veya lokal ortamında MongoDB ayaktayken bu scriptin hatasız "13/13 Passed" sonucunu vermesi. Kırılan adımları bana iletmen durumunda anında fix branch'i açılacaktır.
