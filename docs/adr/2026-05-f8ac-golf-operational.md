# ADR — F8AC Golf Operational Stress

**Date:** 2026-05-24
**Status:** Accepted (spec written, full-suite verification pending)
**Series:** F8 Stress Test Roadmap → Tier-1 (gap analiz 2026-05-24, kullanıcı seçimi)
**Sister of:** F8AB Spa & Wellness Operational Stress (aynı doctrine, kardeş yüzey)

## Context

`backend/domains/golf/router.py` (699 satır), spa modülünün resource-scheduling
pattern'inin birebir kardeşi: kurs katalog (par/holes/slope/rating) + oyuncu
roster + tee-time grid (konfigüre interval + slot capacity) + atomic
çift-katmanlı rezervasyon guard (slot capacity overflow + same player/guest
double-book) + folio entegrasyonu (charge_to_room + completed transition →
folio post + Xchange POSTING_CHARGE publish) + günlük özet. `with_resource_locks`
ile (course, tee_time) anahtarlı atomik rezervasyon, replica-set yoksa
standalone fallback (`is_replica_set_unavailable` + `standalone_fallback_allowed`).

Gap analiz tablosunda F8AC en hızlı kazanım Tier-1 maddesi olarak işaretlendi
(F8AB klonu, aynı `with_resource_locks` + folio safety pattern). Kullanıcı
seçti, spec yazıldı.

## Decision

Tek bir Playwright spec dosyası: `frontend/e2e-stress/specs/98-golf-operational.spec.js`
(module: `golf_operations`). F8AB doctrine'inin birebir uyarlaması.

### Test matrix

| Step | Senaryo | Beklenti |
|------|---------|----------|
| Setup | `/api/golf/courses` + `/api/golf/players` probe; courses auto-seed default kurs döner, players boşsa super_admin POST seed | catalog 200, en az 1 course + 1 player; aksi P2 module-blocked |
| A | Catalog smoke (courses, players, tee-sheet, daily-summary, bookings) | her endpoint 2xx, non-2xx P2 |
| B | Booking lifecycle: confirmed→checked_in→completed (no folio), no_show, cancelled, folio-guard (charge_to_room=True + reservation_id=null) | her transition 200; `completed` 403 olursa P2 (role gap, lifecycle invariant intact) |
| C | **Conflict guard (a):** kapasite kadar party_size ile rezervasyon, sonra +1 oyuncu overflow → 409 zorunlu, 2xx = P1; **(b)** same player_id at same tee_time → 409 zorunlu, 2xx = P1 |
| D | Folio-post endpoint: reservation_id=null → 400 zorunlu; bogus id → 404; replay → 409 (idempotency by `transaction_code='GOLF' + reference=booking_id`) |
| E | Negatif validasyon (unknown course, malformed tee_time, invented_status) + Idempotency-Key replay (same player_id, distinct ids = P1) + **P0 cross-tenant IDOR** (pilot bearer status / delete / folio-post → 4xx zorunlu, 2xx = P0) |
| Z | Cleanup idempotent: DELETE bookings round-trip; ikinci pass 404 zorunlu; players + self-seeded courses unified cleanup loop ile (no DELETE endpoint exposed for players) |

### Folio-posting safety (architect concern parity with F8AB)

`backend/domains/golf/router.py` L558-559:
```python
if body.status == "completed":
    update["completed_at"] = datetime.now(UTC).isoformat()
    if bk.get("charge_to_room") and bk.get("reservation_id"):
        await _post_to_folio(current_user.tenant_id, bk)
```

Hem `charge_to_room=True` HEM `reservation_id` set olmadan `_post_to_folio`
çağrılmaz, dolayısıyla `bus.publish(POSTING_CHARGE)` da tetiklenmez.
F8AC test B-d adımı `charge_to_room=True + reservation_id=null` ile completion
yapar; `assertNoExternalCallsPostBatch` her batch sonunda Xchange dispatch
olmadığını doğrular. Bu sayede gerçek Resend/Iyzico/SXI gibi external
service'lere stress run içinde HİÇBİR çağrı sızmaz.

### `STRESS_COLLECTIONS` extension

`backend/domains/admin/router/stress.py` STRESS_COLLECTIONS listesine
golf koleksiyonları eklendi:
- `golf_courses`
- `golf_players`
- `golf_tee_bookings`
- `golf_locks`

Spec-side DELETE primary cleanup path (bookings için). Players ve self-seeded
courses unified cleanup loop ile (stress_seed=True + stress_prefix tag).
Mid-run abort orphan'ları aynı loop tarafından temizlenir.

### Doctrine invariants (mutlak — F8AB ile aynı)

- `pilot_drift = 0` her test sonunda (try/finally)
- `external_calls = []` her batch sonunda
- `failedTests = 0`, `P0 = P1 = 0`
- Cleanup idempotent (DELETE round-trip, ikinci pass 404)
- module-blocked pattern: courses VEYA players probe 403/404 → A/B/C/D/E
  `test.skip` + P2 informational; Z cleanup + final invariants bağımsız çalışır
- Pilot tenant'a mutation YOK (sadece read)

## Consequences

### Positive

- Golf modülü ilk kez stress kapsamı altında; F8AB spa pattern'inin
  doğrulanmış doctrine'i birebir uygulandı.
- İki katmanlı conflict guard (slot capacity + player double-book) ayrı
  test edildi; F8AB'de tek katmanlı (therapist+room overlap) idi.
- Folio-post endpoint contract'ı (`/bookings/{id}/folio-post`) ek surface
  olarak test edildi (F8AB'de waitlist vardı, golf'ta explicit folio-post).
- Baseline 72 → **73 spec**.

### Negative / Risks

- `with_resource_locks` standalone fallback path test edilmiyor (replica
  set bekleniyor); standalone bir Mongo ile rezervasyon HTTP 503 dönerse
  spec FAIL olur — production'da replica set zorunlu, deployment guard
  ayrı (`docs/REPLIT_OPS_CHEATSHEET.md`).
- Players + self-seeded courses için spec-side DELETE endpoint yok;
  orphan-scrub unified cleanup loop'a güvenir. Loop çalışmazsa stress
  prefix'li rowlar birikir (manual sweep gerekir).
- `daily-summary` revenue/rounds_played hesabı `completed` status'undaki
  booking'lere göre yapılıyor; spec bu metriği assert ETMİYOR (yalnız
  endpoint 2xx). Revenue regression için ayrı kontrat testi gerekirse
  F8AC v2.

### Follow-up

- Full-suite verification: republish sonrası `frontend/e2e-stress`
  full run; verdict ≥ GO WITH WATCH, P0=P1=0, external_calls=[].
- F8AC v2 backlog (eğer ihtiyaç çıkarsa): daily-summary revenue
  consistency assert, standalone-fallback contract test, multi-course
  cross-routing test.

## References

- Spec: `frontend/e2e-stress/specs/98-golf-operational.spec.js`
- Backend: `backend/domains/golf/router.py`
- Pattern source: `frontend/e2e-stress/specs/98-spa-wellness-operational.spec.js` (F8AB)
- Roadmap: `docs/STRESS_TEST_ROADMAP.md` § F8AC
- STRESS_COLLECTIONS: `backend/domains/admin/router/stress.py` L186-195
