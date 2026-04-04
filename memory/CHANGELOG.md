# CHANGELOG

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
