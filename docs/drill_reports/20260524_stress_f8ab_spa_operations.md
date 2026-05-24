# F8AB — Spa & Wellness Operational Stress — Spec Written (2026-05-24)

> **Status:** Spec written + `node --check` PASS + `STRESS_COLLECTIONS`
> orphan-scrub eklendi. Full-suite green verification bir sonraki CI
> turunda yapılacak (F8X–F8AA + F8AB birlikte baseline 68 → 73 spec).
> Bu rapor "spec-written" milestone'unu kaydeder; resmi GREEN baseline
> raporu CI run sonrası ayrıca eklenecek.

## 1) Run künyesi

| Alan | Değer |
|---|---|
| Tarih | 2026-05-24 |
| Faz | F8AB — Spa & Wellness Operational Stress |
| Module | `spa_operations` |
| Spec dosyası | `frontend/e2e-stress/specs/98-spa-wellness-operational.spec.js` |
| Test sayısı | 6 (Setup + A catalog + B lifecycle + C conflict/auto-pick + D waitlist + E IDOR/negative + Z cleanup) |
| Backend değişikliği | `backend/domains/admin/router/stress.py` `STRESS_COLLECTIONS` += `spa_appointments`, `spa_waitlist`, `spa_services`, `spa_therapists`, `spa_rooms`, `spa_locks` (orphan-scrub safety net) |
| Baseline | 68 → **69 spec** (full-suite verification pending) |

## 2) Kapsam

### A) Catalog smoke
`/api/spa/services`, `/api/spa/therapists`, `/api/spa/rooms`,
`/api/spa/availability?date=…&slot_minutes=30`,
`/api/spa/daily-summary?date=…`, `/api/spa/waitlist` — non-2xx = P2
informational. Setup adımında therapists/rooms boşsa stress admin
super_admin yetkisiyle birer kayıt seed eder (`require_catalog` geçer).

### B) Appointment lifecycle
- B1: scheduled → in_progress → completed (charge_to_room=false → folio
  bypass, lifecycle invariant pure).
- B2: scheduled → no_show.
- B3: scheduled → cancelled.
- B4: **Folio-posting safety** — `charge_to_room=True + reservation_id=null`
  → backend guard short-circuits (`_post_to_folio` ve
  `bus.publish(POSTING_CHARGE)` ASLA tetiklenmez). Doğrulama: post-batch
  `assertNoExternalCallsPostBatch` delta=0.

### C) Conflict + auto-pick
- C1: ilk create (therapist+room+slot tuple) → 2xx.
- C2: aynı tuple replay → **409** beklenir; 2xx = P1 finding (atomic
  `_check_conflict` + `with_resource_locks` gap). `expect(dup.status).toBe(409)`
  hard-asserted on 2xx; non-2xx 400/422 defansif rejection olarak
  kabul edilir.
- C3: therapist_id+room_id omit edilirse backend deterministik tek atama
  üretir; `assigned_therapist_id` + `assigned_room_id` zorunlu (toBeTruthy).

### D) Waitlist CRUD + promote
Create → list (verify in result) → patch (status `notified`) → invalid
status (`totally_invalid` → 4xx) → manual promote (real appointment
create with same guest_name) → patch (status `fulfilled`). Tüm
mutation'lar prefix-tagged.

### E) Cross-tenant IDOR + negative validation
- E1: unknown service_id (`00…0` UUID) → 4xx.
- E2: malformed `starts_at` → 4xx (422 expected).
- E3: invalid status (`invented_status`) → 4xx.
- E4: **Idempotency-Key replay** — aynı (service, therapist, room, slot)
  tuple + aynı `X-Idempotency-Key`+`Idempotency-Key` header → same id
  veya 409 (atomic conflict guard) zorunlu. Distinct ids + bothOk 2xx
  = **P1** finding (double-book money risk).
- E5: **P0 cross-tenant IDOR** — pilot bearer stress-created appointment
  `/status` POST + DELETE; pilot bearer stress-created waitlist PATCH +
  DELETE → 4xx zorunlu. 2xx = **P0** tenant guard breach.

### Z) Cleanup + final invariants
- Round-1: DELETE her appointment + waitlist (2xx veya 404 kabul).
- Round-2: idempotency — aynı DELETE second pass 404 zorunlu; non-404
  = P1 (cleanup contract broken).
- Final: `assertNoExternalCallsPostBatch` + `assertPilotDriftZero` her
  test'te `try/finally` bloğunda.

## 3) Mutlak invariant gates

| Gate | Beklenen | Spec'te enforce |
|---|---|---|
| `failedTests == 0` | ✅ | hard-assert (`expect().toBeGreaterThanOrEqual(200/400)`) |
| `FAIL adım == 0` | ✅ | `rec(testInfo, {…, status: 'PASS'/'FAIL'})` annotation |
| `P0 == 0` | ✅ | cross-tenant IDOR 2xx = P0 finding + `expect().toBeGreaterThanOrEqual(400)` |
| `P1 == 0` | ✅ | conflict guard 2xx + idempotency replay distinct ids + cleanup non-idempotent = P1 |
| `external_calls == []` | ✅ | her test finally'da `assertNoExternalCallsPostBatch` |
| `pilot_drift == 0` | ✅ | her test finally'da `assertPilotDriftZero` |
| Cleanup idempotent | ✅ | Z second-pass DELETE → 404 zorunlu |

## 4) Doktrine ve guard'lar

- **Module-blocked pattern**: services/therapists/rooms probe herhangi
  biri 403/404 → `moduleBlocked=true` + P2 informational + A/B/C/D/E
  `test.skip`, Z cleanup + pilot_drift bağımsız çalışır (F8C/D mirror).
- **Folio-posting safety**: spa router `_post_to_folio` koşulu
  `if appt.get("charge_to_room") and appt.get("reservation_id"):` —
  reservation_id=null short-circuit, bus.publish ASLA tetiklenmez.
  MICE 14-spec'te belgelenen "completed → real external dispatch attempt"
  riskini bu spec test edip dry-run gate'in çalıştığını doğrular.
- **RBAC tolerance**: `completed` transition `require_finance` istiyor;
  stress admin super_admin → PASS, 403 olursa P2 informational (role
  gap, lifecycle invariant intact) — fake PASS yok.
- **Stress collections**: `spa_*` koleksiyonları orphan-scrub safety
  net olarak eklendi; primary cleanup spec-side DELETE'lerdir. Tüm
  Spa modeli `tenant_id` scoped + `id` UUID-based — global teardown
  prefix-filter ile her zaman temizler.

## 5) Sonraki adımlar

1. Full-suite CI run (Full Operational Stress Suite + F8X–F8AA + F8AB).
2. Green run sonrası `docs/drill_reports/` altına resmi GREEN baseline
   raporu (69 spec) eklenecek.
3. Roadmap "Latest verified baseline" satırı 68 → 69 olarak güncellenecek.

## 6) İlgili dosyalar

- `frontend/e2e-stress/specs/98-spa-wellness-operational.spec.js` — yeni spec
- `backend/domains/admin/router/stress.py` — `STRESS_COLLECTIONS` += spa
- `backend/domains/spa/router.py` — spec'in test ettiği yüzey
- `docs/STRESS_TEST_ROADMAP.md` — F8AB section + baseline note
- `docs/GOTCHAS.md` — F8 Stress Test Series altında F8AB satırı
- `frontend/e2e-stress/fixtures/stress-helpers.js` — reuse-only
- `frontend/e2e-stress/fixtures/stress-context.js` — reuse-only
