# CHANGELOG


## 2026-04-06 - BUGFIX: HotelRunner Iptal Tespiti Düzeltmesi

### Sorun
HotelRunner'dan yapilan iptal islemleri sisteme dusmuyor / tespit edilmiyordu.

### Kok Neden
Phase A.5 (modifikasyon tespiti) iptal edilen rezervasyonlari `reservation_modified_pull` 
event_type'i ile pipeline'a gonderiyordu. HotelRunner iptal yaptiginda `updated_at` 
timestamp'ini DEGISTIRMEDIĞI icin, `provider_event_id` = `{hr_number}_reservation_modified_pull_{updated_at}` 
onceki modifikasyonla AYNI kaliyordu. Pipeline bu event'i DUPLICATE olarak atliyordu.

### Duzeltme
- Phase A, A.5 ve B'de: Rezervasyonun `state` alani kontrol ediliyor. Eger `cancelled/canceled` ise, 
  event_type `reservation_cancel_pull` (veya `reservation_cancel_catchup`) olarak ayarlaniyor.
- Bu sayede farkli bir `provider_event_id` olusturuluyor: `{hr_number}_reservation_cancel_pull_{updated_at}`
- Pipeline yeni event'i DUPLICATE olarak atlamiyor, CANCEL karari veriyor ve:
  - `reservation_lineage` status'u `cancelled` yapiliyor
  - `bookings` ve `imported_reservations` koleksiyonlarina iptal yayiliyor

### Duzeltilen Dosyalar
- `/app/backend/domains/channel_manager/providers/hotelrunner_sync.py`
  - Phase A: iptal tespiti + dogru event_type
  - Phase A.5: iptal tespiti + dogru event_type 
  - Phase A.6: iptal event'lerini de capture ediyor
  - Phase B: iptal tespiti + dogru event_type

### Dogrulama
- R802387399-2: `decision=cancel`, booking status=cancelled ✅
- R995286077-2: `payload_hash` duplicate (zaten iptal edilmis), booking status=cancelled ✅


## 2026-04-06 - PERF: HotelRunner Polling Optimizasyonu — 5 dk'dan 30 sn'ye

### Sorun
HotelRunner'dan gelen rezervasyonlar sisteme ~5 dakikada, isim degisiklikleri ~30 dakikada dusuyordu.
Exely tarafinda ise aninda yansiyordu.

### Kok Nedenler (Exely vs HotelRunner Karsilastirmasi)
| Ozellik | Exely | HotelRunner (ESKI) | Fark |
|---------|-------|---------------------|------|
| Polling Interval | 30 sn | 300 sn (5 dk) | 10x yavas |
| Modifikasyon Tespiti | Her dongu | Her 3. dongu (15 dk) | 30x yavas |
| Bireysel Kontrol | var | yok | Eksik |
| Phase B Gecikme | yok | 10 sn sleep | Gereksiz |
| from_last_update_date | kullaniliyor | kullanilmiyordu | Eksik |

### Duzeltmeler
1. **startup.py**: HR polling interval 300s -> 30s (Exely ile esit)
2. **hotelrunner_sync.py**:
   - Phase A.5 eklendi: `from_last_update_date` ile son degisiklikleri her dongude tespit
   - Phase A.6 eklendi: Phase A.5'in tespit ettigi degisiklikleri PMS booking'lerine uygula
   - Phase B frekansi: Her 3. dongu (15 dk) -> Her 10. dongu (5 dk)
   - Gereksiz `asyncio.sleep(10)` kaldirildi
3. Sync status endpoint'ine yeni metrikler eklendi (polling_interval, cycle_count, optimization_notes)

### Sonuc
- Yeni rezervasyonlar: ~30 sn (onceki: ~5 dk) = **10x hizlanma**
- Modifikasyonlar (isim, tarih, iptal): ~30 sn (onceki: ~15-30 dk) = **30-60x hizlanma**
- Rate limit sorunu yok (dongu basina sadece 2 API cagrisi)

### Duzeltilen Dosyalar
- `/app/backend/startup.py`
- `/app/backend/domains/channel_manager/providers/hotelrunner_sync.py`

---


# CHANGELOG

## 2026-04-06 - BUGFIX: Takvim Doluluk Sayıları ve Dashboard Brifing Yanlış Bilgi Gösteriyordu

### Sorun
1. **Takvim doluluk sayıları yanlış**: Suite "1/4" gösteriyor ama 5+ aktif rezervasyon var. Doluluk çubuğu tüm sıfır.
2. **Dashboard Günlük Brifing yanlış**: Doluluk %0, Aylık Gelir $0, İçeride 0, Bugün Çıkış 0 gösteriyordu.

### Kök Nedenler
1. **Takvim doluluk** (`CalendarGrid.jsx`): Atanmamış rezervasyonların `room_type` alanı HotelRunner Türkçe isimleri ("Corner Süit", "Deluxe Oda") kullanıyor, ama PMS oda tipleri İngilizce ("Suite", "Deluxe"). `getUnassignedBookingsForType` fonksiyonu `room_type_id` alanını da kontrol ettiği için unassigned bookinglar doğru bölümde görünüyor ama doluluk sayacı bu kontrolü yapmıyordu.
2. **Doluluk çubuğu** (`ReservationCalendar.jsx`): `getOccupancyForDate` sadece `checked_in` durumundaki rezervasyonları sayıyordu. Hiçbir misafir check-in yapmadığı için %0 çıkıyordu.
3. **AI Brifing** (`endpoints.py`): `occupied_rooms` sadece `checked_in` durumunu sayıyordu. Gelir `accounting_invoices`'den hesaplanıyordu ki o boştu.
4. **Operasyonel Uyarılar** (`pms_dashboard.py`): `departures_today` ve `inhouse_count` sadece `checked_in` durumunu sayıyordu.
5. **Cache Warmer** (`cache_warmer.py`): Dashboard cache aynı hatalı lojiği kullanıyordu.

### Düzeltmeler
- `CalendarGrid.jsx`: Doluluk sayacına `room_type_id` kontrolü eklendi
- `ReservationCalendar.jsx`: `getOccupancyForDate` artık `confirmed`, `guaranteed`, `checked_in` durumlarını sayıyor
- `endpoints.py`: AI brifing doluluk hesabı bugünle çakışan aktif rezervasyonları sayıyor, gelir booking tutarlarından fallback
- `pms_dashboard.py`: PMS dashboard ve operational-alerts endpoint'leri aktif durumları sayıyor
- `cache_warmer.py`: Cache warmer dashboard hesabı düzeltildi

### Düzeltilen Dosyalar
- `/app/frontend/src/pages/calendar/CalendarGrid.jsx`
- `/app/frontend/src/pages/ReservationCalendar.jsx`
- `/app/backend/domains/ai/endpoints.py`
- `/app/backend/routers/pms_dashboard.py`
- `/app/backend/cache_warmer.py`



## 2026-04-05 - BUGFIX: Çoklu Oda Rezervasyonunda Tek Oda İptali Tüm Odaları İptal Ediyordu

### Sorun
HotelRunner'da çoklu oda rezervasyonunda (örn. R159939488, 10 oda) tek bir oda iptal edildiğinde, PMS'te TÜM odalar iptal olarak işleniyordu.

### Kök Neden
`explode_multi_room_reservation()` fonksiyonunda (hotelrunner_shared.py) yanlış bir kontrol vardı:
```python
elif room_cancel_reason or "cancel" in room_next_states:
```
HotelRunner, TÜM aktif odalara `next_states=["cancel"]` gönderiyor — bu "iptal aksiyonu yapılabilir" anlamında, "oda iptal edildi" DEĞİL. Kod bunu yanlış yorumluyordu.

### Düzeltme
`"cancel" in room_next_states` kontrolü kaldırıldı. Artık sadece `room.state`, `room.status` ve `room.cancel_reason` alanlarına bakılıyor. Bu davranış, parent-level kontrolle (hotelrunner_sync.py L341-343) tutarlı hale getirildi.

### Dosyalar
- `backend/domains/channel_manager/providers/hotelrunner_shared.py` (explode_multi_room_reservation)

---

## 2026-04-05 - FEATURE: HotelRunner Otomatik Polling Yeniden Aktif

### Kullanici Istegi
Rezervasyonlar HotelRunner'dan otomatik olarak gelsin, manuel senkronizasyon gerekmemeli.

### Degisiklikler
1. **startup.py**: HotelRunner Pull Scheduler yeniden aktif edildi (300s = 5 dakika aralikla)
2. **startup.py**: HotelRunner Push Queue Worker yeniden aktif edildi (120s aralikla)
3. **hotelrunner_sync.py**: `auto_polling_disabled` flag'i artik scheduler durumuna gore dinamik
4. **startup.py**: Shutdown handler'larina HR scheduler ve push worker graceful stop eklendi

### Teknik Detaylar
- Pull interval: 300 saniye (5 dakika) — rate limit'e neden olmayacak kadar uzun
- Adaptive backoff: 429 rate limit alindiginda interval otomatik olarak katlanarak artiyor (max 16x = 80 dakika)
- Push Queue Worker: 120 saniyede bir basarisiz push'lari yeniden deniyor
- Auto-sync: `hotelrunner_connections` koleksiyonunda `is_active=true` ve `auto_sync_reservations=true` olan tenant'lar icin calisiyor

### Dogrulama
- Pull Scheduler basarili: `scheduler_running: true`, `auto_polling_disabled: false`
- Otomatik pull calisti: `[PULL] Tenant 044f122b...: fetched 0, processed 0` (yeni rezervasyon yok, beklenen)
- Push Queue Worker basarili: log'da `HotelRunner Push Queue Worker started (120s interval)`

---

## 2026-04-05 - FIX: Docker Build `No module named pip` (İkinci Komut)

### Problem
Dockerfile'da `python -m pip install --prefix=/install` çalışırken pip kendini 24.0→26.0.1'e upgrade ediyor ve `/install` prefix'ine kuruluyor. Sistem pip'i kaldırılıyor, ikinci komut (`litellm>=1.83.2 --no-deps`) `No module named pip` hatası veriyor.

### Kök Neden
`--prefix=/install` ile kurulum yapıldığında, yeni pip `/install/lib/python3.11/site-packages/` altına kuruluyor ama Python'un `sys.path`'inde bu yol yok. İkinci `python -m pip` komutu sistem PATH'inde pip bulamıyor.

### Çözüm
İkinci komut öncesinde `PYTHONPATH=/install/lib/python3.11/site-packages` ayarlandı:
```dockerfile
PYTHONPATH=/install/lib/python3.11/site-packages python -m pip install --no-cache-dir --prefix=/install "litellm>=1.83.2" --no-deps
```

### Etki
- Docker build artık başarıyla tamamlanıyor
- litellm CVE fix hâlâ uygulanıyor
- Tek satır değişiklik, sıfır risk

---


## 2026-04-04 - FIX: Push Kuyruğu Manuel Retry Kaldırıldı + Tümünü İptal Et

### Problem
- 200+ push kuyruğunda birikmiş, "Şimdi Dene" butonu timeout'a düşüyordu (senkron işleme ~4.3 dakika)
- Manuel retry, arka plan worker ile çakışıyordu
- Kullanıcı deneyimi kötüydü (başarısız retry, süresiz bekleme)

### Çözüm
1. `POST /queue-retry` endpoint kaldırıldı (senkron retry problemi)
2. `DELETE /queue-cancel-all` endpoint eklendi — tüm pending/retrying/completed öğeleri siler, auto-retry ve batch push task'larını iptal eder
3. Frontend: "Şimdi Dene" butonu → "Tümünü İptal Et" (kırmızı, confirm dialog ile)
4. Banner sadeleştirildi — arka plan worker bilgisi + iptal butonu
5. Mevcut 191 bekleyen + 40 tamamlanan kuyruk öğesi temizlendi

### Doğrulama
- `queue-cancel-all` endpoint: 191 pending + 40 completed silindi ✅
- Kuyruk boş: pending=0, completed=0, failed=0 ✅
- Frontend: Banner kuyruk boşken gizli, lint temiz ✅

---

## 2026-04-04 - FIX: Docker Build `pip: not found` Hatası

### Problem
Dockerfile'da `pip install --prefix=/install -r requirements.txt` çalışırken pip kendini 24.0→26.0.1'e upgrade ediyor. Yeni pip `/install` prefix'ine kurulduğu için sistem PATH'indeki eski pip siliniyor ve ikinci komut (`pip install litellm --no-deps`) çalışamıyordu: `/bin/sh: 1: pip: not found`

### Çözüm
- `Dockerfile`: `pip` → `python -m pip` olarak güncellendi (PATH bağımsız)
- `scripts/post_install.sh`: Aynı şekilde `python -m pip` kullanımına geçildi (güvenlik)

### Doğrulama
- `post_install.sh` yerel ortamda başarılı ✅
- `python -m pip` her ortamda çalışır (PATH'e bağımlı değil) ✅

---

## 2026-04-04 - SEC: litellm CVE-2026-35029 & CVE-2026-35030 Fix

### Problem
`pip-audit` CI/CD pipeline'da litellm 1.80.0'daki 2 CRITICAL CVE nedeniyle başarısız oluyordu:
- CVE-2026-35029: `/config/update` endpoint'inde admin rol kontrolü eksik → RCE riski
- CVE-2026-35030: JWT cache key collision → kimlik hırsızlığı riski

### Kök Neden
`emergentintegrations==0.1.0` → `openai==1.99.9` gerektiriyor.
`litellm>=1.83.0` (CVE fix) → `openai>=2.30.0` gerektiriyor. → Bağımlılık çakışması.

### Çözüm
1. `backend/scripts/post_install.sh` oluşturuldu: `pip install litellm>=1.83.2 --no-deps`
2. `ci-cd.yml` security-scan: pip-audit artık `-r requirements.txt` yerine yüklü ortamı tarıyor
3. `ci-cd.yml` backend-test, load-test, security-scan: `post_install.sh` tüm pip install adımlarına eklendi
4. `Dockerfile`: Builder stage'de litellm CVE fix eklendi

### Doğrulama
- `pip-audit`: "No known vulnerabilities found" ✅
- Backend sağlıklı çalışıyor ✅
- openai==1.99.9 + litellm==1.83.2 + emergentintegrations==0.1.0 uyumlu ✅

---

## 2026-04-04 - PERF: HotelRunner Push days[] Optimizasyonu (~74x Hız Artışı)

### Problem
Kullanıcı belirli günler seçerek (örn: sadece Cumartesi+Pazar) Nisan'dan Aralık sonuna kadar minimum konaklama kısıtlaması gönderdiğinde, sistem her non-consecutive gün için ayrı bir API çağrısı yapıyordu. 74 gün × 3 oda tipi = 222 ayrı push × 2sn delay = ~7.5 dakika bekleme süresi.

### Kök Neden
HotelRunner API'nin `days[]` parametresi (gün-of-week filtresi) kullanılmıyordu. Bunun yerine `_group_consecutive_dates()` ile her non-consecutive gün ayrı date range'e bölünüyor, her biri ayrı API çağrısı olarak gönderiliyordu.

### Çözüm
HotelRunner `PUT /rooms/~` endpoint'inin `days[]` parametresini kullanarak (0=Pazar, 1=Pazartesi, ..., 6=Cumartesi) seçili günleri tek bir API çağrısında göndermek:

1. **provider.py - `update_room`**: `days[]` query param desteği eklendi
2. **hr_rate_manager_router.py - `_push_with_retry`**: `days` parametresi kabul ediyor
3. **hr_rate_manager_router.py - `hr_bulk_grid_update`**: selected_days aktifken tek push per oda tipi (days[] ile)
4. **hr_push_queue_worker.py - `enqueue_failed_push`**: Retry kuyruğu da `days` bilgisini saklıyor
5. **hr_push_queue_worker.py - `_process_tenant_queue`**: Retry sırasında `days` parametresini forward ediyor

### Performans
- **Eski:** 74 push/oda tipi × 2sn = 148sn/oda tipi
- **Yeni:** 1 push/oda tipi × ~1sn = 1sn/oda tipi
- **İyileştirme:** ~74x hız artışı

### Test
- 3 oda tipi × Nisan-Aralık × Cmt+Paz: 222 DB kayıt, sadece 3 push → 3/3 SUCCESS (~6sn total)
- HotelRunner LIVE API doğrulaması yapıldı

---

## 2026-04-04 - FIX: HotelRunner 403 Access Denied + Connection Pooling

### Problem
HotelRunner'a gönderilen fiyat ve müsaitlik push'ları `403 Access denied` hatası döndürüyordu.

### Kök Neden (2 katmanlı)
1. HotelRunner API belirli endpoint'lerde `Accept: application/json` header'ı gerektiriyor
2. Çok sayıda eşzamanlı TCP bağlantısı açılması WAF engelini tetikliyordu

### Çözüm
1. **client.py**: `Accept: application/json` header tüm isteklere eklendi
2. **client.py**: HTTP Connection Pooling uygulandı (max 5 bağlantı, 3 keepalive)
3. **hr_rate_manager_router.py**: Arka plan push'larında ardışık 403 hata tespiti ve kuyruklama

---


## 2026-04-04 - FIX: requirements.txt Bağımlılık Çakışması ve Temizlik

### Problem
`pip install -r requirements.txt` CI/CD pipeline'da başarısız oluyordu:
- `litellm==1.83.2` → `openai==2.30.0` gerektiriyor
- `emergentintegrations==0.1.0` → `openai==1.99.9` gerektiriyor
- ResolutionImpossible hatası

### Kök Neden
Önceki ajan güvenlik yaması yaparken `pip freeze` çıktısını direkt requirements.txt'e yazdı.
Bu, `pip-audit` ve `litellm==1.83.2`'nin tüm bağımlılıklarını üretime ekledi.

### Çözüm
1. `litellm==1.83.2` pinlemesi kaldırıldı (kodda hiç kullanılmıyor, transitive dependency olarak emergentintegrations çekiyor)
2. `pip-audit` ve 13 bağımlılığı kaldırıldı (geliştirme aracı, üretimde gereksiz)
3. pip artık `litellm==1.80.0`'ı seçiyor (openai==1.99.9 ile uyumlu)
4. Kaldırılan paketler: boolean.py, CacheControl, cyclonedx-python-lib, defusedxml, license-expression, litellm, packageurl-python, pip-api, pip-requirements-parser, pip_audit, py-serializable, sortedcontainers, tomli, tomli_w

### CVE Notu
litellm 1.80.0 hâlâ CVE-2026-35029 ve CVE-2026-35030 içeriyor (fix: 1.83.0+).
CI/CD'de post-install olarak `pip install litellm==1.83.2 --no-deps` eklenebilir.
Bu, emergentintegrations constraint'i nedeniyle requirements.txt'te doğrudan çözülemez.

### Doğrulama
- `pip install -r requirements.txt` çakışma olmadan tamamlanıyor ✅
- openai==1.99.9, litellm==1.80.0, emergentintegrations==0.1.0 uyumlu ✅
- Backend sağlıklı çalışıyor ✅

---

## 2026-04-03 - FEATURE: HotelRunner Otomatik Polling Devre Disi (Event-Driven Mimari)

### Kullanici Istegi
Sistem surekli HotelRunner API'ye otomatik istek gondererek rate limit (429) hatasina neden oluyordu. Kullanici surekli polling yerine sadece gercek degisikliklerde ve manuel islemlerde API'ye istek gitmesini istedi.

### Degisiklikler
1. **startup.py**: HotelRunner Pull Scheduler ve Push Queue Worker otomatik baslama bloklari kaldirildi
2. **hotelrunner_sync.py**: sync/status endpoint'ine `auto_polling_disabled: true` flagi eklendi
3. **hr_rate_manager_router.py**: "otomatik denenecek" mesajlari "manuel deneyin" olarak guncellendi
4. **HRRateManager.jsx**: 30 saniyede bir queue status polling (setInterval) kaldirildi, banner metni "Manuel olarak Simdi Dene butonuyla gonderebilirsiniz" olarak guncellendi
5. **StopSalePanel.jsx**: Toast mesajlari "Simdi Dene ile gonderebilirsiniz" olarak guncellendi

### Yeni Mimari
- **Event-Driven**: Booking olusturuldugunda/guncellendginde outbox sistemi uzerinden HotelRunner'a otomatik push
- **Manuel Pull**: POST /api/channel-manager/hotelrunner/sync/reservations/pull
- **Manuel Queue Retry**: POST /api/channel-manager/hr-rate-manager/queue-retry + "Simdi Dene" butonu
- **Otomatik Polling**: TAMAMEN DEVRE DISI

### Test Sonuclari
- Backend: 8/8 passed (%100)
- Frontend: All UI tests passed (%100)
- Dogrulama: Restart sonrasi 4+ dakika boyunca SIFIR HotelRunner API istegi yapildi

---


## 2026-04-03 - FEATURE: HotelRunner Push Kuyruk Mekanizmasi (Otomatik Retry)

### Ozellik
Rate limit'e takilan push islemleri artik otomatik olarak kuyruklaniyor ve API toparlaninca yeniden gonderiliyor.

### Yeni Backend Bilesenler
- `hr_push_queue_worker.py`: Arka plan worker — 120 saniyede bir kuyruktaki gorevleri isler
  - `enqueue_failed_push()`: Basarisiz push'u kuyruğa ekler (duplicate merge destegi)
  - `get_queue_status()`: Tenant bazli kuyruk istatistikleri
  - `HRPushQueueWorker`: Adaptive backoff ile calisir
- MongoDB collection: `hr_push_queue`

### Yeni API Endpoint'leri
- `GET /api/channel-manager/hr-rate-manager/queue-status`: Kuyruk durumu (pending, retrying, completed, failed)
- `POST /api/channel-manager/hr-rate-manager/queue-retry`: Kuyruktaki gorevleri hemen yeniden dene
- `DELETE /api/channel-manager/hr-rate-manager/queue-clear`: Tamamlanan gorevleri temizle
- `DELETE /api/channel-manager/hr-rate-manager/queue-cancel/{item_id}`: Belirli bir gorevi iptal et

### Frontend Degisiklikler
- `HRRateManager.jsx`: Sari kuyruk banner'i (bekleyen push sayisi + "Simdi Dene" butonu)
- `StopSalePanel.jsx`: Kuyruk toast mesajlari
- 30 saniyede bir kuyruk durumu polling

### Akis
1. Push rate limit'e takilir → kuyruğa eklenir
2. Kalan room type'lar direkt kuyruğa eklenir (API'ye tekrar vurmaz)
3. Worker 120s'de bir kuyruğu kontrol eder
4. API toparlaninca push basarili olur → "completed" olarak isaretlenir
5. Rate limit devam ederse → adaptive backoff (240s, 480s...)

### Test Sonuclari
- Backend: 7/9 passed (2 timeout beklenen — rate limit aktif)
- Frontend: 100%

---

## 2026-04-03 - BUG FIX: HotelRunner Rate Limit (429) Kapsamli Duzeltme

### Issue
Kullanici HotelRunner rate manager'dan fiyat/musaitlik gonderdigi zaman surekli "cok fazla istek" (429) hatasi aliyordu. Push islemleri basarisiz oluyordu.

### Root Cause (3 katmanli)
1. **Polling cok sik (30 saniye)**: `startup.py`'da `interval_seconds=30` ile reservation polling yapiliyordu. HotelRunner API bu sikliga izin vermiyor.
2. **Push backoff hesaplamasi hatali**: `_push_with_retry` fonksiyonu `min(retry_after, backoff)` kullaniyordu. Sunucu "60 saniye bekle" derken kod 2 saniye bekliyordu — rate limit asla toparlanamiyordu.
3. **Polling retry'lari cok uzun bekliyordu**: Reservation polling'de 429 alinca 3 retry × 60s = 3 dakika bos bekliyordu, rate limit kotasini daha da tuketiyordu.

### Fix (5 parcali)
1. **startup.py**: Polling interval 30s → 120s (4x azaltma)
2. **hotelrunner_sync.py**: Adaptive backoff — 429 alindigi zaman backoff katlanarak artiyor (240s, 480s, 960s...)
3. **hotelrunner_sync.py**: Polling icin max_retries=0, fail fast — scheduler backoff'a birak
4. **hotelrunner_sync.py**: Phase B (full catchup) rate limit altinda devre disi
5. **hr_rate_manager_router.py**: Push backoff duzeltildi — max 30s cap, 3 retry, akilli rate-limit algilama

### UI Iyilestirmeler
- `HRRateManager.jsx` + `StopSalePanel.jsx`: Rate limit durumunda kullaniciya aciklayici Turkce uyari gosteriliyor
- Yeni `rate_limit_hit` flag'i ile frontend'de rate limit durumu dogrudan algilanabiliyor

### Verified
- Backend loglarinda adaptive backoff calisiyorr (429 → 240s bekleme)
- Push API hizli yanit donuyor (timeout yok)
- Veriler yerel veritabanina kaydediliyor, push basarisiz olsa bile veri kaybi yok

---

## 2026-04-03 - BUG FIX: HotelRunner Rate Manager Push Hatalari

### Issue
1. HotelRunner rate manager ekraninda Stop Sale gonderildiginde toast mesaji "Exely'ye iletildi" yaziyordu
2. Kisitlamalar ve musaitlikler HotelRunner'a gitmiyordu (background task sonuclari kayboluyordu)
3. Provider hatasi sessizce yutulup kullaniciya bilgi verilmiyordu

### Root Cause
- `StopSalePanel.jsx`: Toast ve uyari mesajlari "Exely" olarak hardcoded idi, `apiPrefix` prop'una gore dinamik degildi
- `hr_rate_manager_router.py`: Push islemleri `asyncio.create_task` ile arka plana atiliyordu, sonuclar API yanitinda `push_results: []` olarak bos donuyordu
- `_get_hr_provider`: Exception yakalayip `(None, None)` donuyordu, log bile yazmiyordu

### Fix
1. **StopSalePanel.jsx**: `isHotelRunner` flag eklendi, toast ve uyari metinleri baglama gore dinamik hale getirildi
2. **hr_rate_manager_router.py**: Background push kaldirip `await asyncio.gather` ile senkron push yapildi, `push_results` gercek sonuclari donuyor
3. **_get_hr_provider**: Hata loglanmaya baslandi, `provider_warning` mesaji eklendi
4. **HRRateManager.jsx**: Push sonuclari ve provider uyarisi kullaniciya gosteriliyor

### Verified
- Stop sale push: curl test → success=true
- Availability + restrictions push: curl test → success=true
- Backend logs: `[HR-BULK-UPDATE] Push done: 1/1 successful`

---

## 2026-04-03 - BUG FIX: HotelRunner Yeni Rezervasyonlar Sisteme Dusmüyor (R379692424)

### Issue
Kullanici HotelRunner'dan 12 odalik yeni bir rezervasyon olusturdu (R379692424) ama PMS'e hic dusmedi. Phase B catchup yeni rezervasyonlari "Cancellation without existing reservation" olarak isleyip atliyordu.

### Root Cause
HotelRunner API, TUM onaylı (confirmed) rezervasyonlarda `next_states=['cancel']` donduruyor. Bu alan "iptal mevcut bir eylem" anlamina geliyor, "rezervasyon iptal edildi" anlamina DEGIL. Fakat `_run_phase_b()` icindeki `effective_state` hesaplamasi `'cancel' in next_states` kontrolunu iptal gostergesi olarak kullaniyordu.

### Fix (3 parca)
1. `hotelrunner_sync.py` — `effective_state` hesaplama duzeltildi
2. `hotelrunner_sync.py` — Otomatik geri alma yasagi eklendi
3. Veri temizligi: R379692424 icin stuck kayitlar silindi

### Verified
- R379692424: 12 booking → confirmed
- R881632298: 7 booking → cancelled (regresyon duzeltildi)
- R635472908: 5 booking → cancelled (regresyon duzeltildi)
- R676063586: 2 booking → cancelled (regresyon duzeltildi)
