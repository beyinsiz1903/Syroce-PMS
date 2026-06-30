# ADR — CM-Hardening Series (May 2026)

Channel Manager pilot readiness sırasında uygulanan hardening turları. Her tur ayrı PR ile merge edildi; bu doküman digitalocean.md'deki dense gotcha entry'lerinin tam detayını taşıyor.

---

## Turu #1a — Overbooking Conflict Alert Emission

`core/atomic_booking.create_booking_atomic` artık `BookingConflictError` raise'inden hemen önce `_emit_overbooking_alert(...)` çağırıyor — `lock_conflict` event'i artık sessiz değil.

İki best-effort yazım:
1. `db.notifications` `'overbooking_risk'` (severity=warning) row
2. `AlertDeliveryService.deliver_alert(...)` (email/Slack/Teams/webhook channel config'i olan tenant'lara)

Her iki yazım da geniş try/except içinde — booking flow'u ASLA bloklamaz, `BookingConflictError` her durumda fırlatılır (cancel-flow `handle_cancellation` notifications insert paterniyle simetrik). `connector_id="*"` → tenant'ın tüm uygun kanallarına broadcast.

**Dedup**: `AlertDeliveryService` fingerprint+throttle (default 300s) zaten korur; `db.notifications` per-attempt row (her conflict attempt ayrı physical event olduğu için kasıtlı).

**Kanca noktası tek** (`atomic_booking.py:368-380`) — 7+ catch site'ı (b2b/agency_portal/marketplace/pms_bookings/departments) değiştirmeden tüm akışları kapsar.

**Test pinleri** (5/5 PASS): `tests/test_overbooking_alert_emission.py`
- T1+T2 notification yazıldı + metadata
- T3 `notifications.insert_one` boom → conflict yine raise
- T4 `deliver_alert` boom → conflict yine raise + notification independence
- T5 multi-night attempt'te `conflict_night` doğru failing night
- T6 OOO bloğu çakışması → `conflict_type="ooo"` + Türkçe label

**Test side-effect**: integration testlerde yüksek-load conflict simülasyonu sonrası `db.notifications` ve `cm_alert_fingerprints` cleanup gerekebilir.

---

## Turu #1b — Conflict Queue API

Turu #1a sinyal kanalını açtı, Turu #1b çözüm halkasını kapattı: yeni router `backend/routers/cm_conflict_queue.py` (`/api/channel-manager/conflict-queue`) — `GET` liste + `GET /count` (KPI badge için lightweight) + `POST /{booking_id}/resolve` body `{room_id}`.

**Resolve mekanizması**: `_claim_room_for_pending_booking` helper'ı `core.atomic_booking._night_dates` + `_timeline_event` reuse eder, kendi loop'unda her gece için `room_night_locks.insert_one` (aynı unique-index, INV-1/INV-2 paterni); DuplicateKey'de partial-claim compensation (`delete_many` claimed list) + timeline event `"conflict_resolve_failed"` + 409 (`conflict_night` + `conflicting_booking_id` body'de). Başarıda `bookings.update_one` ile `room_id` set + `allocation_source="front_desk_resolve"` (yeni enum) + best-effort `db.notifications` `"overbooking_resolved"` insert.

**RBAC**: `Depends(require_op("edit_booking"))` 3 endpoint'te de — front-desk + supervisor + admin + super_admin'in EDIT_BOOKING permission'ı zaten var.

**Registry**: `backend/bootstrap/router_registry.py` `_EXTRACTED_ROUTERS` listesine eklendi.

**Test pinleri** (`backend/tests/test_cm_conflict_queue_api.py`, 6/6 PASS):
- T1+T2 list+count parity
- T3 happy path (room_id atandı + 2 night lock + notification)
- T4 ikinci resolve 404 (idempotency boundary)
- T5 bilinmeyen booking_id 404 (auth scope)
- T6 ilk-gece conflict 409 + body
- T7 (architect follow-up) **mid-stay** conflict — 2-night booking'in 2. gecesi conflict olduğunda 1. gece lock'unun release edildiği

**Bilinen sınırlama**: `room_night_locks.insert_one` ile `bookings.update_one` ayrı işlemler — process crash arasında orphan lock bırakabilir (booking pending, ama oda lock'lu). Self-conflict idempotent, manuel re-resolve 409 verir; orphan-lock cleanup gelecek bir bakım turunda.

**Out of scope**: Conflict Queue UI (Turu #1c), auto-suggest free room (analytics), bulk resolve (Turu #2).

---

## Turu #1c — Conflict Queue UI

Turu #1b backend Conflict Queue API'sine front-desk UI eklendi. Yeni dosya `frontend/src/pages/ConflictQueuePage.jsx` — `ChannelHub`'ın 4. tab'ı olarak embedded mode'da render edilir (`Çakışmalar`, `AlertTriangle` ikon).

**UI bileşenleri**:
- 3'lü `KpiCard` (bekleyen sayı intent warning/success, etkilenen kanal sayısı info, 30s refresh periyodu neutral)
- Tablo: `guest_name` + `ChannelChip` + `room_type` + dates + `formatCurrency` total + `external_confirmation` + "Oda Ata" Button
- Resolve dialog: `room_type` ile filtrelenmiş Select + "İlk Müsaiti Öner" auto-suggest button
- 30s auto-refetch

**409 hata davranışı**: `toast.error` `conflict_night` + `conflicting_booking_id` ile (8s duration).

**Architect follow-up'lar uygulandı**:
1. `invalidateQueries({queryKey: ['pms']})` doğru namespace — önce yanlışlıkla `['pms-bookings']` kullanılmıştı, hiçbir query bu key'le kayıtlı değildi → Arrivals/Calendar refresh edilmiyordu
2. `onError` da `QK_LIST` + `QK_ROOMS` invalidate eder — başka bir personel oda kapmış olabilir (race), stale veri ile retry loop önlenir

**Değişen dosyalar**: `frontend/src/routes/sections/lazyPages.js` (lazy export), `frontend/src/pages/ChannelHub.jsx` (4. tab + ALL_TABS + grid-cols-4 + AlertTriangle import + i18n key `channelHub.tabs.conflicts`).

**Konvansiyonlar**: axios baseURL `/api` olduğu için relative path WITHOUT `/api`, `formatCurrency`, `<Button variant="outline" size="sm">` Yenile, indigo/amber palet, dialogs (sonner toast).

**i18n**: page içeriği şu an hardcode TR (mevcut Hardening turu konvansiyonu) — teknik borç.

**Available rooms**: `GET /pms/rooms?status=available&limit=2000` + client-side `room_type` filter (fallback: type match yoksa tüm available).

**Out of scope**: standalone route (embedded prop hazır, ileride PageHeader ile kullanılabilir), bulk resolve (Turu #2'de geldi), server-side `room_type` filter, drag-drop reassign.

---

## Turu #2 — Conflict Queue Bulk Resolve

Turu #1b/#1c'nin tek-tek resolve akışına ek olarak toplu (batch) atama eklendi.

**Backend**: `POST /api/channel-manager/conflict-queue/bulk-resolve` body `{items: [{booking_id, room_id}, ...]}` (max 50, RBAC `require_op("edit_booking")`); response her zaman 200 + `{succeeded: [], failed: [], total, resolved_by}` — partial success normal kabul edilir.

**Per-item işleme**: `_claim_room_for_pending_booking` helper'ını yeniden kullanır (her booking kendi atomik lock kazanımı; bir item'ın conflict'i diğer success'leri rollback etmez — `create_booking_atomic` paterniyle simetrik).

**De-dup**: aynı `booking_id` iki kez gelirse last `room_id` wins (race önleme). Pre-load: tenant rooms tek round-trip (set lookup, N+1 önleme).

**Failure error kodları**:
- `room_not_available` (`conflict_night` + `conflicting_booking_id` ile)
- `room_not_found` (cross-tenant veya geçersiz id)
- `not_pending` (zaten resolve edilmiş veya yok)

**Frontend** (`ConflictQueuePage.jsx`): Checkbox kolonu + `Set<booking_id>` selection state + items refresh'te otomatik cleanup `useEffect`; "Toplu Ata (N)" header CTA (`Layers` icon, ≥1 seçili iken görünür); bulk dialog (max-w-2xl) per-row Select + "Tümünü Otomatik Ata" button (same-type filter, batch içinde double-assignment önler — `used` Set); seçili row'lar `bg-amber-50/40` highlight; mixed result toast (warning, 8s); başarılı satırlar selection'dan düşer, başarısızlar retry için kalır.

**Cache invalidation**: `onSettled` `QK_LIST` + `QK_ROOMS` + `['pms']` (success/error fark etmez, race-safe).

**Test pinleri** (`tests/test_cm_conflict_queue_api.py`, 8/8 PASS, 26.25s):
- T8 `test_bulk_resolve_partial_success_does_not_abort_batch` — 1 success + 1 conflict, succeeded[]/failed[] populate, success row promotion + lock count, failure leftover lock=0
- T9 `test_bulk_resolve_invalid_room_id_reported_per_row` — bogus `room_id` `room_not_found`, batch continues

**Out of scope**: WebSocket push (Turu #3 candidate), standalone `/conflicts` route (Turu #4), full i18n (Turu #5), AI room scoring (Turu #6).

---

## Turu #3a + #3b — No-Show OTA Outbox Parity

**Turu #3a (Outbox event production)**: `handle_no_show` artık `release_booking_nights` + audit yazımının ardından `enqueue_outbox_event(BOOKING_NOSHOW="booking.no_show.v1")` çağırıyor — `handle_cancellation` paterniyle simetrik.

**Payload**:
```python
{
  "booking_id", "guest_id", "room_id",
  "check_in", "check_out", "property_id",
  "previous_status", "new_status": "no_show",
  "marked_by", "no_show_at",
  "inventory_released": True,
}
```

Sıralama bilinçli: outbox'tan ÖNCE inventory release çalışır, böylece `inventory_released: true` payload'da gerçeği yansıtır.

**Dispatcher mapping**: `outbox_dispatcher.EVENT_TYPE_TO_CM_EVENT["booking.no_show.v1"] = "booking_no_show"` (L26).

**Turu #3b (HotelRunner inventory recompute, Strategy A)**: `EventSyncService.SUPPORTED_EVENTS` + `EVENT_SYNC_MAP` + `_extract_date_range` üçlüsüne `booking_no_show` eklendi → event artık `booking_cancelled` ile aynı `InventorySyncService.trigger_inventory_sync` yoluna giriyor (HR `push_daily_inventory` → `PUT /api/v2/apps/rooms/daily`).

**Discovery sonucu**: `HotelRunnerProvider`'da `cancel_booking`/`mark_no_show` benzeri transactional metod **YOK** — cancel bile sadece envanter recompute kullanıyor; no-show için aynı pattern doğru tercih (hayalet endpoint riski yok). Pilot için kritik olan kazanım: oda HR ARI'sinde geri açılır, tekrar satılabilir görünür. Guest-level `"no_show"` status'u HR'a iletilmez.

**`outbox_dispatcher._build_cm_payload`**: booking-event tuple'ına `booking_no_show` eklendi (payload schema drift'e karşı parity).

**Çift-emit koruması iki katmanlı**:
1. Terminal-state guard ikinci no-show çağrısını 400 ile durdurur — outbox enqueue'ya hiç ulaşmaz
2. Outbox `idempotency_key=tenant:event:entity:payload_hash` yedek savunma

**Test pinleri**:
- `tests/test_reservation_noshow_e2e.py` T9+T10 (outbox event üretimi + double-emit guard) 10/10 PASS
- `tests/test_reconciliation_complete.py` `test_booking_no_show_routed_like_cancelled` (Strategy A wiring + `trigger_inventory_sync` called with correct kwargs) + `test_booking_cancelled_regression_unchanged` (parity reference)

Outbox enqueue exception'ı sessiz log'lanır (cancel paterniyle simetrik, transition asla bloke edilmez).

---

## Turu #3c — Exely No-Show Parity (DISCOVERY COMPLETE — Mayıs 2026)

Pilotta Exely müşterisi yok → uygulama **DEFERRED**. Bu bölüm discovery turunun (kod yazılmadan) tam mimari haritasını çıkarır; gelecekteki implementasyon turu için referans dokümandır.

### Mevcut akış haritası (Mayıs 2026)

**Outbox → EventSyncService akışı (Turu #3a + #3b ile çalışan kısım — ✅)**:
1. `core/outbox_dispatcher.py:25` → `EVENT_TYPE_TO_CM_EVENT["booking.no_show.v1"] = "booking_no_show"` (Turu #3b'de eklendi)
2. `core/outbox_dispatcher.py:64-71` → `EventSyncService.handle_event(tenant_id, "booking_no_show", payload)` çağrılıyor
3. `channel_manager/application/event_sync_service.py:23-44` → `booking_no_show` zaten `SUPPORTED_EVENTS` + `EVENT_SYNC_MAP[booking_no_show] = SyncType.INVENTORY` + `_extract_date_range` üçlüsünde
4. `event_sync_service.py:72` → `repo.get_active_connectors(tenant_id, property_id)` ile aktif connector'lar çekiliyor
5. Her connector için `InventorySyncService.trigger_inventory_sync(...)` → `_dispatch_single_event` → provider push

**Akış HR tenant'larında doğru çalışıyor**, çünkü HR connector'lar `connector_accounts` koleksiyonunda (`channel_manager/infrastructure/repository.py:48-51` bu koleksiyonu sorgular) ve `_dispatch_single_event` (`channel_manager/application/inventory_sync_service.py:792-803`) `ConnectorProvider.HOTELRUNNER` branch'ine sahip.

### Discovery'nin asıl bulgusu — iki ayrı CM modülü, iki farklı enum

Repo'da **iki paralel CM kod tabanı** var:

| Modül | `ConnectorProvider` enum | Bağlantı koleksiyonu |
|---|---|---|
| `backend/channel_manager/` (event sync, dispatch) | `HOTELRUNNER, SITEMINDER, CHANNEX` (`domain/models/connector_account.py:18`) — **EXELY yok** | `connector_accounts` |
| `backend/domains/channel_manager/` (provider push, ARI) | `HOTELRUNNER, EXELY` (`data_model.py:29`) | `hotelrunner_connections` + `exely_connections` (ayrı) |

EventSyncService (`backend/channel_manager/`) **Exely'yi tanımıyor** — ne enum'da, ne dispatch branch'inde, ne de connector koleksiyonunda. `_dispatch_single_event` (`backend/channel_manager/application/inventory_sync_service.py:792-805`):

```python
if connector.provider == ConnectorProvider.HOTELRUNNER:
    # ... HR push
else:
    raise ValueError(f"Unsupported provider: {connector.provider}")
```

### Exely tenant'ı için fiili davranış

`get_active_connectors(tenant_id, property_id)` `connector_accounts` koleksiyonunu sorguluyor → Exely conn'lar oraya yazılmadığı için **boş liste** döner → `event_sync_service.py:74` → `{"handled": True, "sync_jobs_created": 0, "reason": "No active connectors"}` → `outbox_dispatcher.py:75-77` "No active connectors → mark as processed" diye **sessizce yutuluyor**.

**Sonuç**: Exely-only tenant'lar için `booking_no_show` (ve `booking_created/cancelled/modified` da!) gerçek-zamanlı push ALMIYOR — sessizce drop ediliyor. Periyodik `exely_pull_worker.py` (180s interval) ve `availability_reconciliation_worker.py` (15min interval) gap'i kısmen kapatıyor, dolayısıyla pilot süresince katlanılabilir.

### `ExelyProvider` push yetenekleri

`backend/domains/channel_manager/providers/exely/provider.py:222-254` → tek push metodu `push_ari(room_type_code, rate_plan_code, start_date, end_date, availability, rate_amount, ...)`. Rate ve availability'yi tek call'da birleşik gönderir (iki SOAP RQ üretir: `OTA_HotelRateAmountNotifRQ` + `OTA_HotelAvailNotifRQ`). Ayrı `push_availability`/`push_rates` metodu **YOK** — `_dispatch_single_event`'taki HR pattern'ine (`client.push_availability(updates)` / `client.push_rates(updates)`) doğrudan map etmiyor. Adapter gerekecek.

### Gelecekteki implementasyon — iki strateji

#### Strategy A — Minimal Hook (~4-6 saat) ⭐ ÖNERİLEN

`EventSyncService.handle_event` içinde köprü:
1. Mevcut `connector_accounts` lookup'ı sonrası `exely_connections` koleksiyonunu da kontrol et (yeni repo helper: `get_active_exely_connections(tenant_id, property_id)`)
2. Bulunan her Exely conn için `_dispatch_single_event` yerine **yeni `_dispatch_exely_event` helper** çağır — `unified_rate_manager_router._push_to_exely` mantığına benzer doğrudan ARI recompute (room mapping → `provider.push_ari` for affected dates)
3. `_dispatch_single_event` ve `ConnectorProvider` enum'una **dokunma** — sıfır breaking change
4. Test: 2-3 unit (Exely conn varsa no_show event recompute tetikler / yoksa skip / HR + Exely birlikte aktifse ikisi de tetiklenir)

**Avantaj**: HR-only tenant'lar etkilenmez, schema migration yok, geri çevirmesi kolay.
**Dezavantaj**: İki connector path paralelde — teknik borç birikir, aynı pattern başka eventler için tekrarlanır.

#### Strategy B — Full Unification (~1-2 gün)

1. `backend/channel_manager/domain/models/connector_account.py:ConnectorProvider`'a `EXELY = "exely"` ekle
2. `_dispatch_single_event`'a `EXELY` branch ekle: `ExelyClient` adapter (push_availability/push_rates) → mevcut `push_ari` üzerine wrapper
3. Schema migration: `exely_connections` → `connector_accounts` (discriminator field veya view); pilot Exely müşterisi yok = sıfır risk
4. `repository.py` ve `unified_rate_manager_router._push_to_exely` unified path'e refactor
5. 8-10 unit + integration test

**Avantaj**: Tek source-of-truth, gelecekteki tüm event türleri otomatik Exely desteği alır, teknik borç temizlenir.
**Dezavantaj**: Daha geniş etki yüzeyi, schema migration test'i gerekir, refactor regression riski.

### Öneri

**Strategy A** post-pilot'ta ilk Exely müşterisi geldiğinde ya da gerçek bir blocker oluştuğunda. **Strategy B** Q3 2026 mimari turu için (CapX/HotelRunner gibi yeni connector eklenirken birlikte yapılmalı). Pilot süresince **mevcut periyodik scheduler kapsamı yeterli** (180s + 15min) — discovery'de gerçek-zamanlı push gap'inin pilot için katlanılabilir olduğu doğrulandı.

### Discovery turunun ürettiği değişiklikler

**Kod**: 0 satır (sadece keşif).
**Doküman**: bu bölüm + `digitalocean.md` gotcha güncellemesi (eski Strategy etiketleri ve path referansları düzeltildi).

---

## Turu #4 — Stop-Sale Circuit Breaker

Persistent gateway outage'larda (504/timeout flood, DNS taşması) provider push'ları log/CPU spam'i üretiyordu. Mevcut `provider_failover.CircuitBreaker` (`backend/domains/channel_manager/provider_failover.py:21`) sınıfı vardı ama **hiçbir provider çağırmıyordu**.

**Yaklaşım 1 — Standalone breaker integration**: `execute_with_failover` semantiği yanıltıcı (single-provider için aşırı abstraction); inline check ile `is_available` → fail-fast, post-call `record_success`/`record_failure`.

**Per-connection key**: `f"{provider}:{connection_id or '_default'}"` — bir kötü tenant diğerlerini tripletmesin. Singleton `provider_failover.get_breaker(key)` sayesinde mevcut admin endpoint'leri (status/reset) otomatik çalışır.

**Sarılan metodlar**:
- HotelRunner: `push_daily_inventory` + `push_date_range_inventory` (aynı `hotelrunner:{conn_id}` breaker'ını paylaşır) — `provider.py:410, 466`
- Exely: `push_ari` (rate+avail iki SOAP call'u tek breaker altında, ikisi de fail ise 1 record_failure) — `provider.py:235`

**Retry policy interaction**: `HotelRunnerRetryPolicy` breaker'ın **altında** çalışır. Breaker sadece post-retry sonucu görür → transient flutter'lar (3-attempt retry'ın yediği 504'ler) breaker'ı tripletmez. Sadece persistent outage'lar.

**Fail-fast dönüşü** (breaker OPEN iken):
```python
ProviderResult(
    success=False,
    error="circuit_open: HotelRunner breaker is OPEN for connection {conn_id}",
    error_type="CircuitOpen",
    metadata={"circuit_open": True, "circuit_state": breaker.get_status()},
)
```
HTTP call YAPILMAZ. Outbox dispatcher mevcut backoff ile yeniden dener; breaker `recovery_timeout=60s` sonra HALF_OPEN'a geçer.

**Default breaker config**: `failure_threshold=5`, `recovery_timeout=60s`, `half_open_max_calls=3`.

**Test pinleri** (8/8 PASS): `tests/test_provider_circuit_breaker.py`
- T1 başarılı push CLOSED tutar, breaker etkisi yok
- T2 5 ardışık fail → OPEN, 6. çağrıda HTTP yapılmaz, `error_type=CircuitOpen` + `metadata.circuit_open=True`
- T3 `recovery_timeout` sonrası HALF_OPEN; `half_open_max_calls` başarı → CLOSED + failure_count=0
- T4 HALF_OPEN'da fail → OPEN'a geri
- T5 conn-A trip → conn-B etkilenmez (per-connection isolation)
- T6 Exely `push_ari` aynı pattern, `exely:{conn_id}` namespace'inde — HR namespace ile çakışmaz
- T6b **Concurrent HALF_OPEN admission bounded** — `half_open_max_calls + 5` paralel task gönderildiğinde tam olarak `half_open_max_calls` kadarı admit edilir, kalan `CircuitOpen` döner (regression guard for non-atomic is_available + record_success race)
- T7 `push_daily_inventory` ve `push_date_range_inventory` aynı per-conn breaker'ı paylaşır

**Code-review fixleri (architect feedback, May 2026)**:
1. **Per-connection key collapse → fixed**: HR `factory.py` ve 5 ExelyProvider call site (unified_rate_manager_router, availability_reconciliation_worker, availability_auto_sync, rate_manager_router x2) artık `connection_id=f"{tenant_id}:{property_id_or_hotel_code}"` geçiyor. Önceden boş `connection_id` → tüm tenant'lar `_default` breaker'ını paylaşıyordu (cross-tenant interference).
2. **Tenant-scoped /circuit-breakers → fixed**: endpoint artık `current_user.tenant_id` ile başlamayan breaker key'lerini reddeder; `connection_id` response'ta tenant prefix'i strip edilmiş halde döner (cross-tenant observability leakage önlemi).
3. **HALF_OPEN admission race → fixed**: yeni `CircuitBreaker.try_acquire()` atomic metodu — `is_available` check + HALF_OPEN slot rezervasyonu tek call'da. Wrappers `is_available` yerine `try_acquire()` kullanır. Python tek-thread + GIL nedeniyle bu metot içinde await yok = naturally atomic.

**UI (UnifiedRateManager)**:
1. Yeni endpoint `GET /api/channel-manager/unified-rate-manager/circuit-breakers` — per-provider breaker özeti (severity rule: OPEN > HALF_OPEN > CLOSED, varsayılan CLOSED). RBAC: `view_system_diagnostics`.
2. Header altı pill banner: yalnızca ANY breaker `state != closed` ise görünür (sağlıklı durumda gürültü yok). Kanal sağlığı: `ShieldCheck/AlertTriangle/ShieldAlert` ikonları, emerald/amber/rose intent.
3. 30s interval refetch + bulk update sonrası 1.5s'de tek-shot refetch.
4. `handleBulkUpdate` toast'u akıllılaştı: `channel_push_count > 0 && breaker.state == 'open'` → warning ("kayıt yazıldı, push tekrar denenecek"); `half_open` → warning ("kısmen yanıt veriyor"); else success.

**Out-of-scope** (bilinçli):
- `_push_to_hotelrunner`/`_push_to_exely` arka plan task'ları senkron `succeeded[]/failed[]` döndürmez (asyncio.create_task fire-and-forget). Senkron partial-success UI bu mimaride mümkün değildi → breaker status banner + akıllı toast pragmatik replacement.
- HR `update_room` (legacy single-row push) sarılmadı — `push_daily_inventory`/`push_date_range_inventory` modern path; bg push worker bunları kullanır.
- `push_ari_bulk` HotelRunner'da sequential `update_room` çağırır (henüz sarılmamış). İleriki tur kapsamı.
