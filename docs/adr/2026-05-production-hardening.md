# ADR — Production Hardening Series (May 2026)

Pilot readiness'in CM dışı production hardening turları. Her tur ayrı PR ile merge edildi; bu doküman digitalocean.md'deki dense gotcha entry'lerinin tam detayını taşıyor.

---

## No-Show Terminal-State Guard

`ReservationStateMachine.handle_no_show` artık `NON_NOSHOWABLE_STATES = {"checked_in", "checked_out", "cancelled", "no_show"}` guard'ı çağırıyor (cancel'daki `NON_CANCELLABLE_STATES` paterniyle simetrik).

**Önceden**: `validate_transition` `current==new` durumunda `(True, "no_change")` döndüğü için ikinci no-show çağrısı 200 dönüyor + duplicate audit row yazıyordu.

**Şimdi**: ikinci çağrı 400 + duplicate audit YOK.

**Hata mesajı**: `"Cannot mark reservation as no_show in '{state}' state"`.

**Test pinleri**: `tests/test_reservation_noshow_e2e.py` T3 invert (`test_double_noshow_blocked_by_terminal_state_guard`) — `audit_count == 1` assertion.

**Önemli not**: `frontdesk_service_v2.process_no_show` zaten kendi idempotent yolunu (200 + `idempotent: True`, audit yazmaz) koruyor — bu hardening sadece pms-core state-machine yolunu (`POST /api/pms-core/no-show`) etkiler.

---

## No-Show Inventory Lock Release

`handle_no_show` artık `release_booking_nights(reason="no_show:{marked_by}")` çağırıyor — `handle_cancellation` paterniyle INV-6 simetrisi tamamlandı.

**Önceden**: no-show booking'leri terminal olduğu hâlde `room_night_locks` koleksiyonunda kalıyor, aynı tarih aralığında ARI'yi yapay olarak kısıtlıyordu.

**Şimdi**: `_timeline_event` `"lock_released"` eventi de otomatik yazılır (`reason="no_show:..."` metadata ile).

**Test pini**: `tests/test_reservation_noshow_e2e.py` T8 (`test_noshow_releases_room_night_locks`) — pre-locks>0 → no-show 200 → post-locks==0.

**Hata fallback**: `release_booking_nights` exception fırlatırsa `logger.warning` + transition başarılı (silent-fail; cancel'daki paternin aynısı, audit asla bloke edilmez).

---

## Closed Folio Refund/Void Guard

`FolioHardeningService.post_refund/void_charge/void_payment` artık `folio.status != "open"` iken 4xx döner.

**Önceden**: refund/void için guard yoktu — `post_charge`/`post_payment` ile asimetrikti.

**Hata mesajı**: `"Folio is {status}, cannot post refunds|void charge|void payment"`.

**Test pinleri** (`tests/test_folio_charge_payment_e2e.py`):
- T9 `test_refund_on_closed_folio_blocked` (eski `_succeeds_GAP` ters çevrildi)
- T10 `test_void_charge_on_closed_folio_blocked`
- T11 `test_void_payment_on_closed_folio_blocked`

5/5 closed_folio testleri PASS.

**Operasyonel not**: Kapalı folio'da düzeltme gerekirse: önce `re-open` (admin akışı) veya `transfer-to-city-ledger` üzerinden adjustment.
