# CHANGELOG

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
