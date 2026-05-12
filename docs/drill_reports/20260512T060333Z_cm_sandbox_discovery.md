# Channel Manager Sandbox Discovery — Pilot Readiness

**Date**: 2026-05-12T06:03:33Z
**Scope**: Stop-sale push · No-show OTA sync · Overbooking alerting
**Type**: Discovery (no code changes; planning artefact)
**Trigger**: Production hardening turları #1 (Closed-Folio Refund/Void Guard) ve #2 (No-show Terminal-State Guard + Inventory Lock Release Mini-Tur) sonrası — pilot kalan en yüksek riskli alan: Channel Manager sandbox semantiği.

---

## Yönetici Özeti

| # | Risk Alanı | Öncelik | Effort | Pilot Blocker? |
|---|---|---|---|---|
| 1 | Overbooking conflict alerting & resolution UI | **P0** | M | Evet (sessiz `pending_assignment` riski) |
| 2 | No-show OTA sync — outbox + adapter parity | **P1** | M | Hayır, ama OTA tarafında "Active" görünme riski yüksek |
| 3 | Stop-sale push — circuit breaker + partial-success UI | **P2** | S | Hayır (idempotency + sandbox stub mevcut) |

**Net karar**: P0 kapanmadan pilot CM uçtan uca güvenli değil. P1 pilot içinde tolere edilebilir ama operasyon ekibi günlük manual reconciliation döngüsüne hazır olmalı. P2 pilot sonrası fast-follow.

---

## 1) Overbooking Conflict Alerting & Resolution (P0)

### Mevcut durum
- **Engelleme katmanı sağlam**: `core/atomic_booking.py:112-255` `create_booking_atomic` → `room_night_locks` (tenant_id, room_id, night_date) unique index. INV-1 + INV-2 race-safe.
- `ReservationStateMachine.check_overbooking` (`reservation_state_machine.py:43-56`) manuel rezervasyon + oda taşıma öncesi (front_desk_service.py:162) çağrılır.
- `BookingConflictError` fırlatıldığında `event_timeline.lock_conflict` stage'i yazılır (`atomic_booking.py:208`).
- OOO/OOS blokları aynı kilit mekanizmasını kullanır (`atomic_booking.py:355`).

### Kritik gap'ler
- **Sessiz `pending_assignment` düşürme**: OTA'dan gelen rezervasyon conflict ile reddedildiğinde `room_id=None + allocation_source=pending_assignment` olarak DB'ye yazılır; **personele aktif uyarı gitmez** (in-app toast / red badge / email yok).
- **Conflict resolution UI yok**: Personel `pending_assignment` listesini bulup manuel oda kaydırması yapmak zorunda. Dashboard sekmesi mevcut değil.
- `event_timeline.lock_conflict` yazılır ama hiçbir downstream consumer onu push notification'a bağlamıyor.

### Önerilen hardening
| Adım | Dosya | Effort |
|---|---|---|
| Conflict alert dispatcher | `core/atomic_booking.py:208` → `alert_delivery_service` köprüsü | S |
| Conflict Queue API | yeni `routers/cm_conflict_queue_router.py` (GET pending_assignment + POST resolve) | M |
| Conflict Queue UI | `frontend/src/pages/cm/ConflictQueue.jsx` (KpiCard + tablo + tek-tık oda öner) | M |
| WebSocket push | `notification_events_router.py` extend (event="cm_conflict") | S |

**Pilot blocker rationale**: Çakışan OTA bookingleri sessiz biriktirilirse front-desk haberdar olmaz; misafir varış anında oda yokluğu krizi yaşanır.

---

## 2) No-show OTA Sync — Outbox + Adapter Parity (P1)

### Mevcut durum
- `pms_hardening.py:268` `api_no_show` → `ReservationStateMachine.handle_no_show` → `asyncio.create_task(sync_availability_after_booking(...))`.
- `availability_auto_sync.py._do_sync` oda tipinin tüm envanterini yeniden hesaplayıp push eder (yalnız etkilenen oda değil — veri tutarlılığı +).
- Cancellation flow ile **availability push paralel**, ama event-level paralel **değil**.

### Kritik gap'ler
- **Outbox parity yok**: `BOOKING_CANCELLED` outbox event'i var (`reservation_state_machine.py:178-199`), `BOOKING_NOSHOW` yok. No-show sync tamamen `asyncio.create_task` fire-and-forget — ağ hatası olursa OTA güncellenmez ve **retry yapacak mekanizma yok**.
- **OTA "Active" kalma riski**: Exely / HotelRunner availability push'u alır ama booking statüsünü "no_show" olarak işaretleyen `OTA_HotelResNotifRQ` adapter çağrısı yok. Booking OTA tarafında hâlâ "check-in bekliyor" görünür → reconciliation worker false-positive üretebilir.
- Recently fix edilen inventory lock release (mini-tur, May 2026) **PMS tarafında** çözüldü; OTA tarafında availability push sadece "yeni durumu" yansıtır, no-show **olayını** iletmez.

### Önerilen hardening
| Adım | Dosya | Effort |
|---|---|---|
| `BOOKING_NOSHOW` outbox event tipi tanımı | `core/outbox_service.py` | XS |
| `handle_no_show` → outbox enqueue (cancel paterni) | `reservation_state_machine.py:213-260` | S |
| Exely adapter `OTA_HotelResNotifRQ` "NoShow" status | `domains/channel_manager/providers/exely/*` | M |
| HotelRunner adapter equivalent (provider docs check) | `providers/hotelrunner/*` | M |
| E2E test: no-show → outbox row → provider stub assert | `tests/test_no_show_ota_sync_e2e.py` (yeni) | S |

**Pilot tolere rationale**: Availability push çalışıyor (oda tekrar satılır), sadece OTA dashboard'unda "Active" görünme süresi ~1-3 dk uzar. Reconciliation worker bunu dakikalar içinde temizler. Pilot'ta günlük night audit reconciliation raporu şart.

---

## 3) Stop-sale Push — Circuit Breaker + Partial Success UI (P2)

### Mevcut durum
- Endpoint: `POST /api/channel-manager/unified-rate-manager/bulk-grid-update` (`unified_rate_manager_router.py:525`).
- Servis zinciri: Router → `ARIEventBuffer` (`outbound_service.py:111`) → `coalesce_events` → `compile_delta` → `RateLimitService` → ProviderAdapter.
- HotelRunner: `update_room(stop_sale=True)` (`hotelrunner_ari_adapter.py:63`).
- Exely: `OTA_HotelAvailNotifRQ` (`exely_ari_adapter.py:99`).
- **Idempotency**: `outbound_service.py:159` `provider_delta_hash` ile mükerrer push bloklu.
- **Sandbox**: Her adapter'da `if not self._client` dry-run path var → CI sandbox safe.

### Mevcut testler
- `test_unified_rate_manager_api.py`, `test_stop_sale_scheduler_holidays.py`, `test_p5_stop_sale_deposits.py`, `test_p3_delta_debounce.py`, `test_p2_ari_stress.py`, `test_hrv2_dry_run.py`, `test_hr_parity.py` — kapsam **iyi**.

### Kritik gap'ler
- **Circuit breaker olgunlaşmamış**: 429 rate-limit korumalı ama provider 5xx döngüsünde tüm push'ları durduran genel bir circuit-breaker `hard_fail_gate.py` seviyesinde tam değil — provider çökerse spam log + retry storm riski.
- **Partial success UI**: Bulk update'te fiyat kabul + stop-sale red durumunda UI net göstermiyor; operatör yanılabilir.

### Önerilen hardening
| Adım | Dosya | Effort |
|---|---|---|
| Circuit-breaker state field eklemek | `outbound_service.py` ARI engine stats (L264) + `hard_fail_gate.py` extend | S |
| Stop-sale sandbox harness scenario | `ari/provider_test_harness.py` | XS |
| Partial-success response schema + UI badge | `unified_rate_manager_router.py` response model + `frontend/src/pages/cm/UnifiedRateManager.jsx` toast | S |

**Pilot tolere rationale**: Mevcut idempotency + sandbox dry-run pilot için yeterli güvenlik sağlıyor. Pilot sonrası fast-follow.

---

## Dosya Referans Atlası

```
backend/channel_manager/                           # Hexagonal: application/connectors/domain/infrastructure/interfaces
backend/domains/channel_manager/
  ├─ availability_auto_sync.py                     # _do_sync (no-show + cancel push)
  ├─ sync_scheduler.py                             # pull cycles (HotelRunner retries: manual=3, scheduled=2)
  ├─ unified_rate_manager_router.py                # bulk-grid-update L525 (stop-sale entry)
  ├─ outbound_service.py                           # ARIEventBuffer L111, idempotency L159, ARI engine stats L264
  ├─ providers/exely/exely_ari_adapter.py          # OTA_HotelAvailNotifRQ L99 (sandbox path: if not self._client)
  ├─ providers/hotelrunner/hotelrunner_ari_adapter.py  # update_room(stop_sale=True) L63
  └─ reconciliation_engine, drift_detector.py, auto_heal_service.py, quarantine_service.py
backend/core/
  ├─ atomic_booking.py                             # create_booking_atomic L112-255, room_night_locks unique index, lock_conflict L208
  └─ outbox_service.py                             # BOOKING_CANCELLED present, BOOKING_NOSHOW missing
backend/modules/pms_core/
  └─ reservation_state_machine.py                  # check_overbooking L43-56, handle_cancellation outbox L178-199, handle_no_show L213-260
backend/routers/
  └─ pms_hardening.py:268                          # api_no_show → asyncio.create_task(sync_availability_after_booking)
```

---

## Önerilen tur sırası (post-discovery)

1. **CM-Hardening Turu #1 — Overbooking Conflict Alerting (P0)**: `lock_conflict` → `alert_delivery_service` + WebSocket event. Yeni Conflict Queue router + minimal UI rozeti. **~M**.
2. **CM-Hardening Turu #2 — No-show OTA Sync Parity (P1)**: `BOOKING_NOSHOW` outbox event + handle_no_show enqueue + Exely/HR adapter no-show status. **~M**.
3. **CM-Hardening Turu #3 — Stop-sale Hardening (P2)**: circuit-breaker state + partial-success badge. **~S**.

Pilot karar matrisinde:
- **P0 olmadan pilot canlı CM ile başlamamalı** (kontrollü dry-run sandbox kabul).
- **P1 pilot başında tolere edilebilir**, ancak günlük reconciliation drill şart.
- **P2 pilot içinde fast-follow** (operasyon kuralı: "stop-sale toplu push sonrası UI doğrulaması zorunlu").

---

## Sandbox Drill Önerileri (kod yazmadan operasyonel)

Pilot sandbox'ta önce manuel drill ile davranışı gözlem altına almak — kod yazmadan boşa risk azaltır:

| Drill | Beklenti | Gözlem aracı |
|---|---|---|
| Stop-sale toplu push (10 oda × 7 gün) | provider_delta_hash idempotent dedup, ARI engine stats `pushed_count` artar | `outbound_service.py` stats endpoint |
| OTA-side simulated booking same-day overlap | `BookingConflictError` → `pending_assignment`, `event_timeline.lock_conflict` | `db.event_timeline.find({"stage":"lock_conflict"})` |
| No-show + immediate availability re-pull | `room_night_locks` 0 (mini-tur fix doğrulaması) + provider `Avail` push log | `db.room_night_locks.count`, provider stub log |
| HotelRunner 504 storm (2 ardışık cycle) | scheduled 2 retry, manual 3 retry; 3. cycle sıfırlanır | sync_scheduler logs |

Drill çıktıları `docs/drill_reports/<UTC>Z_cm_sandbox_drill_<n>.md` formatında kayda geçer.

---

## Out of Scope (bu discovery'de değerlendirilmedi)

- Booking.com / Expedia / Agoda direct adapter parity (mevcut: HotelRunner + Exely)
- Rate Plan derivation engine (BAR/derived rate cascade)
- Long-stay / package rate edge cases
- Group booking CM round-trip
- Backup automation (Celery + S3/GCS) — ayrı discovery turu

---

## İmza

Discovery — Replit Agent (kod yazmadan, salt-okuma + analiz turu).
Architect verdict for prior hardening rounds: PASS (Turu #1, #2, Mini-Tur).
Bu rapor `replit.md` Gotchas içine eklenmedi (operasyonel drill artefaktı, kod kuralı değil).
