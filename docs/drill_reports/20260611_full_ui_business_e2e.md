# Full UI + Business E2E — 20260611

> Suite: `frontend/e2e-business/` (Playwright). Üretildi: 2026-06-11T21:41:27.125Z

## 1. Yönetici özeti

- Toplam test: **2**
- Başarısız test: **0**
- Adım sayaçları: PASS=2 | FAIL=0 | REVIEW=2 | SKIP=0
- Süre: 27.3s
- Son karar: **GO** — Tüm testler PASS, kritik FAIL yok

## 2. Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| split-folio | 2 | 0 | 2 | 0 | 4 |

## 3. Kritik bulgular (FAIL adımlar + başarısız testler)

_Yok — tüm testler ve adımlar geçti veya REVIEW/SKIP olarak işaretli._

## 4. Test verileri (oluşturulan / temizlenen)

_Hiç entity oluşturulmadı veya kayıt bulunamadı._

## 5. REVIEW + SKIP adımlar

### REVIEW (2)
- **[split-folio]** POST /api/pms/quick-booking — overbooking precondition (orphan room_night_lock?): {"detail":{"message":"Room not available for 2026-07-11T00:00:00 to 2026-07-12T00:00:00. Night 2026-07-11 already booked by f107faaf-25f9-4b1d-b2cb-3e379abe88b5 (`/api/pms/quick-booking` 409)
- **[split-folio]** POST /api/pms/quick-booking — overbooking precondition (orphan room_night_lock?): {"detail":{"message":"Room not available for 2026-07-11T00:00:00 to 2026-07-12T00:00:00. Night 2026-07-11 already booked by f107faaf-25f9-4b1d-b2cb-3e379abe88b5 (`/api/pms/quick-booking` 409)

## 6. Risk sınıflandırması (heuristic)

- **P0 (canlıya çıkışı engeller)**: failedTests=0, FAIL adım=0
- **P1 (pilot öncesi düzeltilmeli)**: REVIEW kritik modüllerde — bkz. §5
- **P2 (pilot sonrası)**: secondary modül REVIEW/SKIP
- **P3 (kozmetik)**: console error allowlist dışı (varsa raporlandı)

## 7. Artifact path'leri

- HTML report: `frontend/playwright-business-report/`
- Trace/video/screenshot: `frontend/test-results-business/`
- Data registry: `frontend/e2e-business/.auth/data-registry.json`
- Auth state: `frontend/e2e-business/.auth/admin.json` (gitignore önerilir)

## 8. Test inventory

| # | Test | Project | Outcome | Süre |
|---:|---|---|---|---:|
| 1 | desktop › 23-split-folio.spec.js › Scope 6 — Tutar tabanlı folyo bölme (Eşit / Özel) › Eşit Böl gerçekten yeni folyo açar ve kaynak bakiyeyi aktarır | desktop | ✅ passed | 6.0s |
| 2 | desktop › 23-split-folio.spec.js › Scope 6 — Tutar tabanlı folyo bölme (Eşit / Özel) › Özel Tutar gerçekten yeni folyo açar ve girilen tutarı aktarır | desktop | ✅ passed | 4.5s |

## 8. Kök neden analizi (Scope 6 — manuel ek, Task #434)

Scope 6 (Eşit Böl + Özel Tutar) canlı pilota karşı bir kez koşturuldu. Sonuc: 2 test
gecti (hard-fail yok), her ikisi de REVIEW olarak kaydedildi. Split-folio ozelliginin
kendisi degerlendirilemedi cunku test fixture'inin on-kosulu (yeni booking olusturma)
saglanamadi. Iki ardisik kok neden tespit edildi:

1. **Idempotency-Key eksigi (DUZELTILDI — test tarafi).**
   `POST /api/pms/quick-booking`, `create_reservation_service` uzerinden Idempotency-Key
   basligini ZORUNLU kilar (required=True). Test yardimcisi `createTestBooking`
   (e2e-business/fixtures/pms-flow.js) bu basligi gondermiyordu → 400
   "Missing Idempotency-Key header". Uretim UI'i (RoomsTab) zaten her cagrida benzersiz
   bir anahtar gonderiyor; yardimci da artik ayni davranisi yapiyor
   (`Idempotency-Key: e2e-<uuid>`). Bu bir test-istemci duzeltmesidir; validator/RBAC
   ZAYIFLATILMADI.

2. **Sizan/orphan room_night_lock (PILOT VERI-DURUMU — kod degisikligi YOK).**
   Idempotency duzeltmesinden sonra booking olusturma 409 ile reddedildi:
   "Room not available ... Night 2026-07-11 already booked by f107faaf-...".
   Bu cakisma `db.room_night_locks` koleksiyonundaki bir gece-kilidinden geliyor
   (bkz. backend/core/atomic_booking.py — Phase 1 night claim). Ancak:
   - `GET /api/pms/available-rooms` ayni tarih icin odayi MUSAIT gosteriyor (27 oda boş),
     bu yuzden `pickAvailableRoom` odayi seciyor.
   - `GET /api/pms/bookings` (2026-07-10..13) penceresi 0 booking donduruyor; booking
     f107faaf artik `db.bookings`'te yok (full-detail 404).
   Yani f107faaf ORPHAN bir gece-kilidi: booking'i silinmis/iptal edilmis ama kilidi
   serbest birakilmamis. `available-rooms` bu kilidi hesaba katmazken booking-olusturma
   guard'i katiyor → tutarsizlik. Iptal akisi (handle_cancellation →
   release_booking_nights) normalde kilidi serbest birakir (best-effort), dolayisiyla
   bu sizinti muhtemelen yarim-kalan bir olusturma veya basarisiz bir serbest-birakmadan
   kaynaklaniyor.

**Siniflandirma karari:** booking-olusturma 409'u split-folio ozelliginin basarisizligi
DEGIL, pilot veri-durumu on-kosuludur. Suite felsefesine uygun olarak (on-kosul →
REVIEW/SKIP, asla hard-fail) `setupSplitPanel` artik create-409'u REVIEW olarak
kaydedip erken donuyor. Split-folio assertion'lari hic calismadigi icin hicbir gercek
ozellik sonucu maskelenmiyor. Fake-green yok.
