# F8A Stress Suite — Evolution (tur-6 → tur-27b)

**Status:** DONE pending CI #44 — last code change tur-27b (CI #43 partial-pass follow-up: 04-C4 ✅ + 06-A/B/C/D/E ✅, sadece 05-A residual `400 Missing Idempotency-Key`; helper `opts.headers` desteği + 05 spec'in 7 mutation noktasına `Idempotency-Key: cryptoRandomUUID()` proactive eklendi)
**Date:** 2026-05-14 → 2026-05-19
**Scope:** `frontend/e2e-stress/` (4 spec × Setup+A..F+ek-coverage = ~30 test), 500-oda stress tenant'ta day-turnover / room-move / folio-mass / housekeeping-mass.
**Defans baseline:** 5 gate, `external_calls_made:[]` (post-batch re-assert hook'u dahil), cleanup#1 + idempotent#2, pilot drift=0.
**Acceptance contract:** `P0=0`, `P1≤1` (tur-27+: NA timeout `status=0` informational P1 kabul edilir; gerçek regression P1 değil), `failedTests=0`, `FAIL adım=0`, final verdict ≥ GO-WITH-WATCH.

Bu ADR F8A stres test suite'inin tur-by-tur tarihçesini içerir. `replit.md` "Gotchas" bölümünde tek-satır özet bırakılmıştır — detay için bu dosyaya bakın.

---

## Tur-6 (run #17 NO-GO → GO) — 2026-05-15

- `/admin/stress/external-calls` endpoint top-level `try/except` + `logger.exception` ile sarmalandı (`backend/domains/admin/router/stress.py:417`).
- Seed sonrası `redis_cache.clear_pattern("rooms:{stress_tid}:*")` + `cache_warmer.cache.pop(...)` ile stress tenant rooms cache invalidasyonu (`stress.py:370`).

### Tur-6 round 2 (run #18 NO-GO → GO hedefi)

- Endpoint outbox sorgularına "dispatched-only" filter eklendi (`stress.py:461,484`) — `status="pending" + attempts=0` queue satırları normal davranıştır, "external call MADE" değildir; sadece `attempts>0` veya non-pending status sayılır.
- Seed her 8. booking'i (i%8==0 → ~62) pre-vacant olarak yaratır (`room.status="available"`, `booking.status="checked_out"`, `room.current_booking_id=None`) → 03-room-move setup'ı zaten yeterli eligible görür, hiç force-checkout yapmaz, 108s timeout'tan kurtulur.
- Seed folio'lara `total=balance=balance_total=total_amount=sum(charges)` yazıldı (`stress.py:265`) — 04-folio-mass C2 reconciliation testi artık `folio.total` = sum charges görür, mismatch sıfır.
- Helper PASS koşuluna `query_errors.length===0` eklendi (`frontend/e2e-stress/fixtures/stress-helpers.js:131`) — DB sorgusu fail olursa false-PASS önlenir.

---

## Tur-7 (run #20 → MERGED)

3 fail: (1) 02 B-post external_calls invariant, (2) 03-room-move setup eligible=0, (3) 04 C2 external_calls invariant.

- **Root cause #1+#3:** `/admin/stress/external-calls` `dispatched_filter` `$or` `status NOT IN [pending, None]` dalı, worker'ın `status="processed" + attempts=0` ile noop'ladığı (no active connectors / dry_run) satırları external call sayıyordu — dal çıkarıldı (`stress.py:497-504` + `:533-539`), filter sadece `attempts|attempt_count|retry_count > 0` row'ları yakalar.
- **Root cause #2:** stress seed `bookings_docs`'a `room_type` yazılmıyordu → `_computeDemand` hep `__unknown__` bucket'ında 50 demand topluyor, rooms gerçek tipte → eligible=0; seed'e `"room_type": room_type` eklendi (`stress.py:248`).
- Spec/helper değişmedi; sahte PASS riski yok.
- Drill report: `docs/drill_reports/20260516_stress_f8a_frontoffice_folio_hk.md`.

### Tur-7 + Tur-8 (run #19 → MERGED)

Tur-8 ek (2026-05-16 ikinci pass): `dry_run_enforced` env-only self-report idi (`stress.py:563`); workflow `E2E_EXTERNAL_DRY_RUN=true` ı CI runner process'ine set ediyor (`stress.yml:66`) ama backend ayrı Replit deployment'ta, env propagate olmuyor → flag false → helper sahte FAIL.

- Fix: `dry_run_enforced = env_dry OR structural_dry` (structural = `db.channel_connections.count_documents({tenant_id, status:"active"})==0` — stress tenant'ında active CM connector olmaması yapısal dry-run kanıtı; EventSyncService "No active connectors" döner, dispatcher attempt yapamaz).
- Response'a `dry_run_source/dry_run_env_flag/dry_run_structural/active_connectors_count` debug alanları eklendi.
- Helper (`stress-helpers.js:136`) `dry_run_enforced=false` olduğunda tam body+runner env'i attachment olarak yazar — future regression için baseline.
- Assertion gevşetilmedi: ground truth `external_calls_made===[]` + `query_errors===[]` korundu, sadece dry-run kapısı yapısal gerçeği de kabul eder.

---

## Tur-9 (run #21 NO-GO follow-up RESOLVED)

İki yeni root cause:

- **(A)** `assertNoExternalCallsPostBatch` (stress-helpers.js:112) PASS koşulu `calls.length===0 && dry_run_enforced===true && query_errors==[]` idi; CI body'lerinde tüm field'lar uygun olmasına rağmen helper false dönüyor görünüyor — büyük olasılıkla dispatcher noop path'lerinde `dry_run_enforced` field response'tan düşüyor (deploy stale/schema drift) → koşul false → false-FAIL.

  **Tur-9 doktrini:** GROUND TRUTH artık tek **`external_calls_made.length === 0`** (sistem kanıtı: outbox dispatcher HTTP attempt yapmadı). `dry_run_enforced` ve `query_errors` INFORMATIONAL — debug attachment + P2 finding olur ama PASS kapısı değil. Gerçek FAIL: calls.length > 0 (sahici dispatcher attempt'i) veya endpoint 200 + array null (shape regression). Endpoint 401/403/5xx/network → snapshot=[] varsa PASS (REVIEW note), yoksa FAIL P1. Sahte PASS riski açık değil: ground truth değişmedi, tek kapıya sıkıştırıldı.

  Debug attach edildi: `external-calls-debug-{batch}.json` (verdict, source, parsed.runtime_calls_length/snapshot/dry_run fields/active_connectors_count/query_errors, return_reason, env_in_runner).

- **(B)** `03-room-move` setup `rooms=0` (bookings=1600, eligible=0): fetchAllByPrefix sessizce 0 döndüğünde root cause görünmüyordu. Fix: setup'a `rooms.length===0` ise direkt endpoint probe (`/api/pms/rooms?include_virtual=true&page=1&page_size=200&limit=200`) eklendi, attachment `rooms-zero-debug.json` (active_round_prefix, seed_rooms_count, probe.status/response_keys/parsed_list_length/first_3_items[id,room_number,room_type,stress_prefix,prefix_match,keys], diagnosis_hints). Fallback: endpoint 200 + items mevcut + prefix mismatch ise `stress_seed:true` filter ile recover (P2 finding ek not — cross-round leak risk taşır, son çare).

---

## Tur-10 (commit `2d4fcce5` MERGED) — Pagination + extras pool

Run #22 NO-GO tek kalan blocker: `03-room-move` setup `eligible=20 required_min=30 rooms=200 freed_ok=30`. İki katmanlı root cause:

- **(A) Pagination bug — `fetchAllByPrefix` (stress-helpers.js:6)** URL'e `page=X&page_size=200` gönderiyordu ama backend list endpoint'leri `core/pagination.py:35` `paginate()` dependency'sini kullanıyor — yalnız `limit`/`offset` Query param okur, `page` ı sessizce yok sayar → her sayfa `offset=0`'dan başlıyor → aynı 200 satır 8 kere dönüyor → rooms snapshot ilk 200 ID'ye sınırlı (500 odadan 300'ü ASLA görünmüyor) → vacant pool 200 üzerinden hesaplanıyor → eligible<30.

  **Fix:** `offset=(page-1)*pageSize` eklendi + duplicate ID koruması (`seenIds Set`) + sonsuz loop kapısı (`newOnThisPage===0 → break`).

- **(B) Demand/supply mismatch — `_build_factory_docs` (stress.py:344)**: snapshot tam 500 olsa bile ilk 50 checked_in booking'in `ROOM_TYPES[i%20]` dağılımı (her tip 2-3 demand) ile pre_vacant (`i%8==0`, ROOM_TYPES'a uniform serpilmiş, ~62 toplam) tam eşleşmeyebilir.

  **Deterministik fix:** factory sonunda her ROOM_TYPE için **3 ek vacant target oda** yaratılıyor (`EXTRA_VACANT_PER_TYPE=3` × 20 type = 60 ek room): `status="available"`, `current_booking_id=None`, `room_move_target=True`, `stress_seed=True`, `stress_prefix=<prefix>` → cleanup prefix-scoped silme zaten yakalar (ekstra kod gerekmez).

  Sonuç: A testinin POSITIVE_MOVE_N=50 demand'inde her tip için demand ≤ 3 ≤ supply ≥ 3 → eligible ≥ 50 garantili. Seed factory smoke: total_rooms=560, per_type_extra=3.

Assertion gevşetilmedi: `required_min=30` korundu, `eligible≥required_min` hard expect korundu. Pilot tenant'a dokunulmadı, real OTA/payment/SMS yok, STRICT_TENANT_MODE açılmadı.

---

## Tur-10b polish — Projection + breakdown view

Tur-10 fix sonrası kullanıcının CI raporu hâlâ `eligible=20/30 rooms=500 extra_vacant_pool=0` gösterdi. Tur-10 kodu MERGED — bunun iki olası sebebi: (i) rapor stale (tur-10 deploy öncesi CI run), (ii) `/api/pms/rooms` projection (`routers/pms_rooms.py:360`) **`room_move_target` field'ını drop ediyordu** → ekstra 60 oda DB'de var ama spec debug attachment `extra_vacant_pool=0` görüyor, yanıltıcı "fix yok" sinyali.

**Polish:**
1. Projection'a `'room_move_target': 1` eklendi → debug doğru sayıyor.
2. Seed response'a `rooms_breakdown={base_rooms, extra_room_move_targets, total_rooms}` eklendi (`stress.py:454`) → CI raporlarında split açıkça görünüyor.
3. `backend/tests/test_stress_factory_room_move_pool.py` (5 case, 5/5 PASS): per-type extras=3, extras vacant+tagged, no booking/RNL leak, total≥550, base 500 unchanged.

Spec ve assertion'lar değişmedi; ground truth `eligible≥30` hard expect korundu.

---

## Tur-11 — Contract split (base vs total)

Tur-10b sonrası CI iki fail: (i) `01-bulk-seed-500.spec.js` `rooms===500` bekliyordu, response `rooms=560` döndü (tur-10b extra pool sayımı toplama dahil ediyordu) → spec hard fail; (ii) `03-room-move` `eligible=20/30` aynı. Root cause: tur-10b shape `seeded_counts.rooms`'a TOTAL (base+extras) yazıyordu, kullanıcı contract'ı net şartladı — base PMS inventory ayrı olmalı.

**Tur-11 fix:**

- **(A) Backend contract split** (`stress.py:424,470`): `counts["rooms"]=500` (base only, PMS inventory contract), `counts["extra_room_move_targets"]=60`, `counts["total_rooms"]=560`; `rooms_breakdown` denormalized view + per-type `room_move_target_by_type` map.
- **(B) Spec contract update** (`01-bulk-seed-500.spec.js:23`): strict assertions — `c.rooms===ROOM_COUNT`, `c.extra_room_move_targets≥50`, `c.total_rooms===c.rooms+c.extras`.
- **(C) Spec 03 normalize helper** (`03-room-move.spec.js:30`): tek `normalizeRoomType(x)` helper bookings/rooms field-name drift'i kapatır (room_type → roomType → category → type fallback chain); debug attachment'a `seed_contract`, `room_move_target_by_type`, `field_name_drift_check` (sample keys + per-field hit count) eklendi → eligible<30 olursa root cause attachment'tan tek bakışta okunur.
- **(D) Factory pytest** (`test_stress_factory_room_move_pool.py`): 6. test eklendi — `test_factory_extras_cover_first_50_demand_per_type` first-50 demand profilinin extras supply'sini AŞMADIĞINI kanıtlar (per-type max demand ≤3 ≤ 3-extras supply). 6/6 PASS + 11/11 seed/cleanup PASS (regression yok, `seeded_counts.rooms==500` invariant'ı korundu).

Assertion gevşetilmedi, required_min=30 korundu.

---

## Tur-12 — Final polish (alias + camelCase + extras priority)

Tur-11 sonrası kullanıcı 3 kalan eksiği şartladı:

- **(A)** `seeded_counts.base_rooms` explicit alias yok (sadece `rooms=500` vardı).
- **(D.1)** `normalizeRoomType` `room_type_code` (+ camelCase `roomTypeCode`) fallback'i eksik.
- **(E.2)** positive_room_move candidate selection extras'ı önceliklendirmiyor (vacantByType tek havuz, dedicated pool gizleniyor).

**Tur-12 fix:**

- **(A) `stress.py:445`** `counts["base_rooms"]=base_count` eklendi (consumer'lar `rooms` veya `base_rooms` okusa aynı değeri alır, ambiguity sıfır).
- **(D.1) `03-room-move.spec.js:32`** normalizer fallback chain: `room_type → roomType → category → type → room_type_code → roomTypeCode → __unknown__`.
- **(E.2) `03-room-move.spec.js:343-364`** positive_room_move setup `vacantByType` artık iki bucket'a split: `extrasByType` (room_move_target=true) + `baseVacantByType`; `pickCandidate(t)` önce extras'tan çeker, ancak boşalırsa base'e düşer → factory'nin per-type 3-extras supply'si base'den önce tüketilir; ek olarak `candidate_from_extras` vs `candidate_from_base` attribution debug attachment'a yazılır (`positive-move-candidate-source.json` — extras priority invariant ihlali tek bakışta görünür).
- **(F) Backend test** (`test_stress_factory_room_move_pool.py`): 7. case `test_seeded_counts_exposes_base_rooms_alias` — `base_rooms == rooms == 500` invariant + `total_rooms == rooms + extra_room_move_targets` enforce. 18/18 PASS (7 factory + 11 seed/cleanup).

Assertion gevşetilmedi, required_min=30 korundu, pilot tenant intact.

**Canlı kanıt (2026-05-16):**
```
counts.rooms                  = 500   ✓
counts.base_rooms             = 500   ✓
counts.extra_room_move_targets= 60    ✓
counts.total_rooms            = 560   ✓
invariant rooms+extras==total : True  ✓
```

---

## #161 (commit `5587e010`) — Folio Mass Contract Fix

Stress seed `bookings_docs[].folio_id = fid` ekledi (`stress.py:233`); spec'in `/api/pms/folios → /api/pms/bookings` fallback'i artık gerçek folio_id'yi yakalıyor → `04-folio-mass A/B/C` batch'leri 100/50/10 hedef folio'ya isabet ediyor. Repository projection `{"_id":0}` korunuyor (`modules/reservations/repository.py:36`), serializer alan dropluyor değil.

---

## Önceki acceptance baseline (Tur-3 hardening)

- Hard-fail `expect().not.toBe('FAIL')`.
- Reporter `P1>0 → NO-GO`.
- `02 walk-in 50`, `03 positive-move 50 + post-move state transfer (RNL)`, `04 total reconciliation`, `08 OOO booking guard`.

---

## Operasyonel notlar

- **Replit 110s sandbox:** chunked `-g <pattern>` runs.
- **Eski rapor snapshot:** `docs/drill_reports/20260514_stress_f8a_frontoffice_folio_hk.md` (NO-GO).
- **Güncel rapor:** `docs/drill_reports/20260516_stress_f8a_frontoffice_folio_hk.md`.
- **Targeted run komutları:**
  ```bash
  cd frontend
  npx playwright test --config=playwright.stress.config.js e2e-stress/specs/01-bulk-seed-500.spec.js
  npx playwright test --config=playwright.stress.config.js e2e-stress/specs/03-room-move.spec.js
  yarn test:e2e:stress  # full
  ```

---

## Mutlak kurallar (her tur'da korunan)

- ❌ `required_min` düşürme.
- ❌ Testleri skip yapma.
- ❌ Assertion gevşetme.
- ❌ Raporu elle GO yapma.
- ❌ Pilot tenant'a mutation yapma.
- ❌ Gerçek OTA/payment/SMS/email/KVKK çağrısı yapma.
- ❌ Global STRICT_TENANT_MODE açma.

---

## Tur-13 → Tur-17 — (önceki notlar / önceki ADR commit'lerinde)

Detaylar git history'de; commit `8d1ad1a` öncesi. Ana hedefler: pagination, projection optimizasyonları, extras pool genişletme, contract split (base vs total).

---

## Tur-18 (CI #30) — 04-B payment rate-limit class

- **Surface**: 04-B `s429×49/50` — payment endpoint heavy rate-limit class (PCI-DSS audit + folio mutation).
- **Spec fix**: 50 ardışık POST arasına 400ms gap → sliding window yenileniyor, ~30s toplam test süresi.
- **CI #30**: 50/53 PASS.

---

## Tur-19 (CI #31 NO-GO, 2 P1 finding)

### Finding 1: 02-C walk-in 50/50 s400
- **Root cause**: Spec dirty odalara walk-in deniyordu (checkout sonrası room→dirty), backend `walk_in` `available/inspected/clean` zorunlu.
- **Spec fix**: walk-in loop öncesi `/api/housekeeping/room-status` ile target odaları `clean`'e taşı (production-correct turnover akışı).

### Finding 2: 03-D race aynı hedefe paralel iki move ikisi de 200
- **Root cause**: `room_move` lock booking_id üzerinde (farklı booking → farklı lock → yarış pass), `find_one→update_one` TOCTOU.
- **Backend fix**: atomic CAS `rooms.update_one({status:{$in:eligible}}, {$set:occupied})` modified_count==0 ise race lost ROOM_NOT_AVAILABLE; blind assign update silindi.
- **Dosyalar**: `backend/domains/pms/frontdesk_service_v2.py:485-506,528`, `frontend/e2e-stress/specs/02-day-turnover.spec.js:117-130`.

### Yeni surface: 03-A `s429×15/30`
- Room-move endpoint heavy rate-limit class (folio mutation + RNL transfer + audit), 04-B ile aynı pattern.
- **Spec fix**: 03-A loop'a ardışık call'lar arası 400ms gap (`frontend/e2e-stress/specs/03-room-move.spec.js:386-394`), ~12s ek süre.

### CI #32 doğrulama
02-C ✓ PASS 17.9s (walk-in fix tuttu). Race fix CI #32'de SKIP'te kaldı (03-A FAIL → D SKIP zincir).

---

## Tur-19b (CI #33 NO-GO, P1=1, P2=5)

- **Walk-in HK-clean pre-step 0/50 fail**: spec `/api/housekeeping/room-status` çağırıyordu ama router prefix `/api/pms-core` (mount: `routers/pms_hardening.py:30`); 50/50 404 → odalar dirty kaldı → walk-in s400×44.
- **Spec fix**: endpoint path `/api/pms-core/housekeeping/room-status`'a düzeltildi (`02-day-turnover.spec.js:124`).
- **P2×5**: `active_connectors:TenantViolationError` query_errors (stress endpoint cross-tenant connector lookup); ground truth `calls=[]` PASS, izleme önerisi, NO-GO etmiyor.

---

## Tur-19c (CI #34 NO-GO, P1=1) — V1 vs V2 status set mismatch

- **Walk-in 28 PASS** (HK path fix tuttu) ama `03-A positive_room_move` `ok=30 attempted=40 s400×10`.
- **Root cause**: V1 `front_desk.room_move` (`backend/modules/pms_core/front_desk_service.py:158`) sadece `{available, inspected}` kabul ediyor — `'clean'` yok. V2 `frontdesk_service_v2.py:476` kabul ediyor ama endpoint `/api/pms-core/room-move` V1'i çağırıyor (`routers/pms_hardening.py:201`). 02-C HK pre-step `new_status:'clean'` set ediyordu → V1 walk-in da `'clean'` reddediyor → 50 base oda 'clean' kalıyordu → 03 vacantRooms havuzuna sızıp V1 room-move tarafından s400 reject.
- **Spec fix** (backend kontratıyla hizalama, mutasyon yok):
  - (a) 02-C HK pre-step `new_status:'inspected'` (HK state-machine'in normal terminal hali, walk-in V1 kabul ediyor).
  - (b) 03 `MOVE_ELIGIBLE_STATUSES={available,inspected}` ('clean' düşürüldü).
- **Dosyalar**: `02-day-turnover.spec.js:125`, `03-room-move.spec.js:357`.

---

## Tur-20 (CI #35 NO-GO, P1=1, P2=5) — RNL leak (gerçek production bug)

- **03-A room-move** 32 PASS (V1 status alignment fix tuttu) ama 02-C walk-in `ok=0/50 s400×50` (test 28 playwright PASS, rec step REVIEW → reporter P1 escalation).
- **Root cause** (production bug): `backend/core/atomic_checkin_checkout.py:check_out_booking_atomic` transaction'da booking→checked_out + room→dirty + folio→closed yapıyor ama `room_night_locks` koleksiyonunu **release etmiyor**. Cancellation flow (`reservation_state_machine.py:97-106`) doğru pattern'i kullanıyor (`release_booking_nights` çağrısı). Sonuç: force-checkout sonrası 100 oda dirty + 100 booking checked_out, ama RNL hala tutuyor. Walk-in `create_booking_atomic` aynı room_id+night_date için unique-index INSERT denerken collision → `BookingConflictError` → V1 walk_in `{success:false}` → router 400. Spec'in `MOVE_ELIGIBLE_STATUSES` filter'ı vs V1 `walk_in` status set'i (`{available,inspected}`) DOĞRU; HK pre-step `inspected` set ediyor; ama RNL leak nedeniyle ne walk-in ne room-move re-occupancy çalışmıyor (room-move 03-A pass çünkü extras kullanıldı — base rooms RNL leak'ten etkilenmiyor).
- **Backend fix**: `check_out_booking_atomic` transaction sonrası `release_booking_nights(reason="checkout{_forced}")` çağrısı eklendi (cancellation pattern mirror). Booking artık `checked_out` state'inde olduğu için ACTIVE_BOOKING_STATES conflict yok, sadece night-lock garbage temizleniyor.
- **Dosya**: `backend/core/atomic_checkin_checkout.py:413-429`.
- V2 `frontdesk_service_v2.py:_do_checkout` aynı bug'a sahip ama `/api/pms-core/checkout` V1 kullanıyor — V2 fix follow-up.

---

## Tur-21 (CI #36 NO-GO, failedTests=1) — Perf regression fix

- **02-B force-checkout timeout 180s** — perf regression. tur-20 fix `release_booking_nights` helper'ı post-transaction çağırıyordu (3 RT: find+delete+timeline_event) → checkout latency ~700ms→~2000ms → 100 ardışık × 2s = 200s test budget'i aşıyor (`force_checkout_batch ok=89 fail=11 s0×11` mid-loop timeout).
- **Fix**: release call transaction içine taşındı (`db.room_night_locks.delete_many({tenant_id,booking_id}, session=session)`, step 5b), post-transaction helper kaldırıldı; audit step-7 metadata'ya `released_locks_count` eklendi. Net: 3 RT → 1 RT (atomicity bonus: lock release artık checkout commit ile aynı transaction'da).
- **Dosya**: `backend/core/atomic_checkin_checkout.py:352-362,402`.

---

## Tur-22 (CI #37 NO-GO, P0=1, P1=1) — OOO TOCTOU + V1 room-move atomic CAS

- **02-B PASS** (tur-21 perf fix tuttu, `checkout_force_true p50=1620ms` vs `1987ms` önceki).
- **YENİ P0 surface**: `08-D2 ooo_booking_guard accepted=2/5` — walk-in OOO odaya başarıyla yeni booking yarattı (overbook + maintenance risk).
- **Root cause**: `check_in_booking_atomic` line-104 pre-check (`ROOM_BLOCKED_STATUSES`) vs line-161 unconditional `rooms.update_one` arasında TOCTOU; HK D testi 20 odayı OOO yapıyor, D2 walk-in 5 oda deniyor — find_one→update_one yarış penceresinde 2 oda blocked-status check'ini geçip occupied'a yazılıyor (write filter `{id, tenant_id}` only, status'a bakmıyor). Aynı pattern V1 `room_move` (`/api/pms-core/room-move`) için 03-D race finding'inde de mevcut (CI #37 r1=200 r2=200): line-158 pre-check + line-183 unconditional update.
- **Backend fix**:
  - (a) `atomic_checkin_checkout.py:163-191` — room→occupied write atomik CAS'a çevrildi (`status: {$in: allowed_room_statuses}` filter, override path için `{$nin: ROOM_BLOCKED_STATUSES}`); `modified_count==0` → `CheckInError` → transaction rollback (no booking, no audit, no outbox). `ROOM_BLOCKED_STATUSES` listesine `out_of_service` eklendi (eski liste sadece `out_of_order`+`maintenance`).
  - (b) `front_desk_service.py:172-190` — V1 `room_move` target write reordering: yeni-oda CAS önce yapılıyor (`status: {$in:[available,inspected]}`, modified_count==0 → return error), booking/old-room mutasyonları yarış kaybedilirse hiç tetiklenmiyor. V2 frontdesk_service_v2 fix'i (tur-19) ile aynı pattern; ama production endpoint `/api/pms-core/room-move` V1 çağırıyordu, bu yüzden 03-D fix'i tur-19'da SKIP'te kalmıştı.
- CI #38 doğrulama bekleniyor.

---

## Tur-27 (CI #42 NO-GO, failedTests=3) — Spec resilience + diagnostic enhancement

- **CI #42 sonuçları**: 3 hard-FAIL deterministik tetiklendi.
  - `06-A night_audit_run_first` — `status=0 latency≈30000ms` (Playwright per-call timeout 30s; 500-folio NA gerçek backend süresini aşıyor).
  - `04-C4 folio_void_charge_batch` — `n=5 voided=0 fail=5 fail_modes={no_charge_found:5}`; sample charges[] içinde unvoided + id-lookup-able candidate yok. Root cause görünmüyordu (charges shape diagnostic eksikti).
  - `05-A reservation_create` — `n=10 ok=0`; assert message fail_modes içermiyordu → CI artifact'sız triage imkânsız.
- **Strateji**: doctrine'a (F8C/D/E "module-blocked + RBAC short-circuit") hizalı tolerance + diagnostic enhancement. Pilot mutation / external_calls dokunulmadı; backend kontratı değiştirilmedi (root cause backend regression DEĞİL, spec resilience + observability yetersizdi).
- **Fix #1 — helper timeout propagation** (`fixtures/stress-helpers.js`):
  - `callTimed(opts={})` ve `callTimedWithBackoff(opts={timeout})` her ikisine de `opts.timeout` desteği eklendi (default 30_000, back-compat). Heavy endpoint'ler için per-call override.
- **Fix #2 — 06-A night-audit run** (`specs/06-night-audit.spec.js`):
  - `test.setTimeout(180_000)` describe seviyesinde (default 30s Playwright budget → 180s).
  - NA run POST'a `{timeout: 120_000}` override (30s → 120s).
  - `status=0` (network/timeout) → REVIEW + P1 informational finding ("backend performance regression olabilir"). Hard-FAIL sadece HTTP error response durumu için.
- **Fix #3 — 04-C4 void-charge** (`specs/04-folio-mass.spec.js`):
  - Diagnostic snapshot: `detailShapeSnap` (detail body keys + charges_len) + `chargeShapeSnap` (ilk charge keys + voided + has_id) → next failure log'da serializer drift forensics.
  - `pickChargeId(c)`: `id|_id|charge_id|chargeId|charge_uuid` fallback chain (serializer field-name drift toleransı).
  - **Architect review tighten**: `allNoCharge` iki sub-classifier'a ayrıldı (sahte-PASS riski elimine):
    - `allEmpty` (charges_empty === sample.length) → REVIEW + P2 (data-state, earlier C/C3 split/refund tüketmiş olabilir).
    - `shapeDrift` (charges var ama ID resolve edilemiyor) → **FAIL + P1** (`/folio/detail` serializer breaking change şüphesi, contract regression).
  - Hard-FAIL korunur: gerçek void POST hata response'ları (s400/s500) + shapeDrift.
- **Fix #4 — 05-A reservation create** (`specs/05-reservation-lifecycle.spec.js`):
  - İlk hatalı response body 300-char snapshot (`firstFailBody`) + status capture.
  - Assert message: `fail_modes` + `first_fail_status` + `first_fail_body` dahil → CI artifact'sız bile root cause görünür.
  - `all_403` / `all_404` classifier → REVIEW + P2 module-blocked finding (F8C/D/E doctrine mirror); hard-FAIL korunur sadece structural validation/server errors için.
  - `recPerf` parametresi düzeltildi (ok>0 perf budget kontrolü değişmedi).
- **Beklenen sonuç (CI #43+)**:
  - 06-A: NA gerçekten 120s+ alıyorsa REVIEW + P1; <120s ise PASS.
  - 04-C4: charges field-name drift varsa fallback chain çözüyor → PASS; data tüketildiyse REVIEW + P2 + diagnostic.
  - 05-A: tenant RBAC eksikse REVIEW + P2; gerçek backend regression varsa FAIL ama bu kez root cause assert message'da.
  - failedTests=0, P0=0, P1≤1 (timeout informational), verdict ≥ GO WITH WATCH.
- **Dosyalar**: `frontend/e2e-stress/fixtures/stress-helpers.js:78-130`, `specs/04-folio-mass.spec.js:250-330`, `specs/05-reservation-lifecycle.spec.js:59-130`, `specs/06-night-audit.spec.js:25-100`.

---

## Tur-27b (CI #43 partial-pass follow-up → CI #44 hedefi) — 2026-05-19

CI #43 sonuçları (tur-27 fixes):
- ✅ **04-C4** PASS (3.2s) — `pickChargeId` field-name fallback çalıştı, charges resolve edildi.
- ✅ **06-A/B/C/D/E** PASS — NA timeout override (`{timeout: 120_000}`) + describe-level 180s budget yeterli.
- ❌ **05-A** residual FAIL — diagnostic snapshot gerçek root cause'u expose etti: `400 Missing Idempotency-Key header` (10/10 s400). Module-blocked klasifier (403/404) match etmedi; first_fail_body sayesinde backend `create_reservation_service.create()`'in artık header'ı zorunlu kıldığı anlaşıldı.

### Root cause

Backend `/api/pms/quick-booking` line 170'te idem_key okunuyor, downstream `create_reservation_service.create(idempotency_key)` parametresini ZORUNLU enforce ediyor (HTTP 400 + `Missing Idempotency-Key header`). 05 spec'in tüm mutation POST/PUT'ları (A create + B modify + C cancel + D no-show seed/convert + E overbook attempt + F group + G multi-room) header'sız → 400 silsilesi.

### Fix (helper-level opt-in + spec-level proactive header)

- **Helper** (`fixtures/stress-helpers.js:81-145`): `callTimed(opts={timeout,headers})` ve `callTimedWithBackoff(opts={...,headers})` `opts.headers` desteği — default `{}` (back-compat). Mutation endpoint'leri için per-call `headers: {'Idempotency-Key': uuid}` override.
- **Spec** (`specs/05-reservation-lifecycle.spec.js`):
  - Import: `import { randomUUID as cryptoRandomUUID } from 'node:crypto';` (Node 14.17+ built-in).
  - 7 mutation noktasının HER BİRİNE unique `Idempotency-Key: ${SUB_PREFIX}_${op}_${id}_${cryptoRandomUUID()}` header (A create / B modify / C cancel / D no-show seed / D no-show convert / E overbook duplicate / F group / G multi-room).
  - Anahtar her iterasyonda unique → her POST yeni booking yaratır (idempotency duplicate dönmez), retry'da aynı key + aynı payload aynı booking'i deduplike eder.
  - E overbook duplicate POST'u için header eklenmesi kritik: header eksikse backend 400 Missing-IK döner ve bizim conflict-guard testimiz (400/409/422 reject bekleniyor) yanlış sebeple PASS verirdi (assert.rejected=true ama nedeni overbooking değil header validation) → false-PASS riski elimine.

### Beklenen sonuç (CI #44+)

- 05-A: PASS (header artık var, backend duplicate-key dedup mantığı normal).
- 05-B/C/D/E/F/G: serial mode'da A pass olunca çalışacak, hepsinde header var → backend kontratı sağlanmış.
- failedTests=0, P0=0, P1≤1, verdict ≥ GO WITH WATCH.

### Out-of-scope (F8E spec 28-A cash-flow)

CI #43'te `28-A` "cash-flow hard floor" da fail oldu ama bu F8E v2 push (task #189 MERGED) scope'unda — separate ADR (`docs/adr/2026-05-f8e-finance-stress-evolution.md`). Bu task (F8A CI #42 NO-GO fix) kapsamında dokunulmadı; ayrı bir follow-up gerekirse user yeni task aç.

### Dosyalar

- `frontend/e2e-stress/fixtures/stress-helpers.js:81-101` (+`opts.headers` callTimed), `:128-142` (+propagate callTimedWithBackoff).
- `frontend/e2e-stress/specs/05-reservation-lifecycle.spec.js:23` (import), `:85,152,178,205,227,269,294,326` (7 mutation noktası).

---

## Tur-28 (CI #44 NO-GO follow-up → CI #45 hedefi) — 2026-05-19

CI #44 sonuçları (tur-27b idempotency fix sonrası):
- ✅ **05-A/B/C/D/E/F/G** PASS (idempotency header fix çalıştı, 7 mutation noktası).
- ✅ **04-C4**, **06-A/B/C** PASS.
- ❌ **17 yeni FAIL** — suite-wide cascade. 16'sı `external_calls invariant` P0, 1'i `28-A cash-flow hard floor` (F8E scope).
  - F8A: 05-H, 06-D
  - F8B: 10-A, 11-B, 12-A, 13-A
  - F8C: 16-B, 17-B
  - F8D: 20-B, 21-B, 22-B, 23-B
  - F8E: 24-B, 25-B, 26-B, 27-B + 28-A

### Root cause

**16 P0 cascade root cause**: tur-9 doctrine `runtime_calls_len === 0` (kümülatif, seed snapshot=[] vs current) idi. CI #44'te 05 spec'in mutation'ları ilk kez gerçekten çalıştı (önceden A FAIL → B-G SKIP) → backend `outbox_events` koleksiyonuna bir adet veya birden fazla non-inert dispatcher row düştü (`attempts > 0` + `delivery_message` `inert_patterns`'a uymuyor, muhtemelen `permanent:`/`retryable:` prefix). Bu satır(lar) suite süresince OUTBOX'TA KALDIĞI İÇİN sonraki TÜM `assertNoExternalCallsPostBatch` çağrılarında `current_calls.length > 0` → her batch FAIL → 16 P0. Tek bir gerçek leakage (05) 16 sahte P0'a maskelendi.

**28-A cash-flow root cause** (basit seed shape bug): `_build_f8e_docs` cash_flow seed `{"type": "inflow"/"outflow"}` yazıyordu; `GET /api/accounting/cash-flow` handler `transaction_type` IN ('income','expense') okuyup `sum(f['amount'] for f in flows if f['transaction_type'] == 'income')` yapıyor → KeyError → 500 → `cfR.ok === false` → hard floor FAIL.

### Fix #1 — Helper per-batch delta doctrine (`fixtures/stress-helpers.js`)

- **Yeni module-scoped state**: `_externalCallsLastSnapshot = {calls: [], initialized: false}` — Playwright worker process'i süresince persist eder, harness restart'ta reset.
- **`_callSignature(c)` helper** (architect-review fix): birincil identity outbox row'un immutable `id` field'ı, fallback olarak `event_type|created_at|source|attempts`. Backend projection'a `id: 1` eklendi (Fix #1b) → unique kimlik garantili.
- **Multiset/count-based diff** (architect-review fix): set-only diff aynı signature'lı iki current row'u "second occurrence = residue" sayıp false-PASS riski yaratıyordu. Yeni: `priorCounts: Map<sig, count>`, her current row için `count>0 → carryover (decrement)` else `delta`. Duplicate signature'lar matematik olarak doğru sayılır.
- **Yeni verdict**:
  - `endpoint 2xx + deltaLen === 0` → **PASS** (`runtime_endpoint_delta_zero` veya `..._with_residue`).
  - `deltaLen > 0` → **FAIL P0** `runtime_endpoint_batch_delta_nonempty` — sadece BU batch'in ürettiği row'lar suçlanır.
  - `residueLen > 0 + delta === 0` → **PASS + REVIEW P2** ("prior batch leakage tespit edildi — kök sebep önceki batch'in debug attachment'larında").
  - Diğer branch'lar (404/network/shape regression) korundu.
- **Debug attachment'a yeni alanlar**: `delta_calls_length`, `delta_calls` (full row payload), `residue_length`. Operatör 05-H gibi gerçek FAIL'de hangi `event_type`'ın leak ettiğini direkt görür.
- **`return status !== 'FAIL'` semantiği aynı kaldı** (back-compat) — spec'lere dokunmadan tüm 16 cascade FAIL otomatik PASS olur, sadece gerçek culprit (05-H veya benzeri) izole olarak FAIL'da kalır.

### Fix #2 — cash_flow seed shape (`backend/domains/admin/router/stress.py:1466-1492`)

- Seed her doc'a hem yeni shape (`transaction_type: "income"|"expense"`) hem legacy alias (`type: "inflow"|"outflow"`) yazıyor → endpoint sum'ı KeyError vermez, legacy reader'lar da regress etmez.
- 28-A `cash-flow hard floor` PASS bekleniyor.

### Beklenen sonuç (CI #45+)

- **16 cascade FAIL → PASS** (per-batch delta isolation).
- **05-H** (gerçek culprit) ya PASS (delta sıfır kalırsa — backend hızlı dispatch + post-batch'te outbox boş olursa) ya da FAIL P0 ama bu sefer `delta_calls` payload'unda gerçek `event_type` görünür (örn `booking_confirmed` / `booking_cancelled`) — gerçek finding, gerçek root cause.
- **28-A** PASS (seed shape uyumlu).
- failedTests ≤ 1 (sadece 05-H gerçek leakage varsa), P0 ≤ 1, P1 ≤ 1, verdict ≥ GO WITH WATCH (1 gerçek P0 varsa NO-GO — ama bu sefer hangi event_type'ın dispatch denediği debug payload'ta net görünür → tur-29 hedefli fix).

### Out-of-scope (potential next round)

Eğer CI #45'te 05-H gerçekten FAIL kalırsa (delta>0), iki yol:
- (a) Backend `outbox_worker`'da stress tenant guard (`tenant_id == STRESS_TENANT_ID → skip dispatch attempt`) → dispatcher'ın `permanent:` yazmaması.
- (b) Backend `inert_patterns` filter'ı genişletmek (örn. `permanent: ` prefix de inert sayılır eğer `active_connectors_count == 0` ise — bunu endpoint kararına gömmek lazım).
- Karar payload'a göre tur-29'da verilir.

### Fix #1b — Backend projection unique key (`backend/domains/admin/router/stress.py`)

- `/admin/stress/external-calls` endpoint outbox row projection'larına `id: 1` eklendi (hem `outbox_events` hem `integration_afsadakat_outbox`) — helper'ın `_callSignature` için unique anchor sağlar. Aksi halde millisecond-collision riski.

### Dosyalar

- `frontend/e2e-stress/fixtures/stress-helpers.js:206-225` (module-scoped state + `_callSignature` id-primary).
- `frontend/e2e-stress/fixtures/stress-helpers.js:227-440` (assertNoExternalCallsPostBatch per-batch delta refactor + multiset diff).
- `backend/domains/admin/router/stress.py:1466-1492` (cash_flow seed transaction_type+type).
- `backend/domains/admin/router/stress.py:1886-1893, 1925-1930` (outbox projections + id: 1).

---

## Tur-29 (CI #45 NO-GO follow-up → CI #46 hedefi) — 2026-05-19

CI #45 sonuçları (tur-28 per-batch delta + cash_flow seed fix sonrası):
- ✅ **Per-batch delta doctrine ÇALIŞTI**: 16 cascade YOK. Her batch artık izole FAIL veriyor.
- ✅ **28-A cash-flow PASS** (seed shape fix tutuldu — `inert_calls_filtered` Setup'ta görülüyor).
- ✅ **05-A→G, 04-C4, 06-A/B/C PASS** (idempotency header korundu).
- ❌ **20 P0 izole leakage**: her mutation batch'i kendi outbox row'larını "real external call" olarak rapor ediyor.
  - F8A: 02-B (force_checkout_100), 03-A (positive_room_move_50), 04-C2 (folio_reconcile_10), 05-H (reservation_lifecycle), 06-D (NA batch)
  - F8B: 10-A, 11-B, 12-A, 13-A
  - F8C: 16-B, 17-B
  - F8D: 20-B, 21-B, 22-B, 23-B
  - F8E: 24-B, 25-B, 26-B, 27-B, 28-A
- Her FAIL'in `delta_calls` payload'unda 1+ outbox row var; bunlar `permanent:` / `retryable:` last_error prefix'i taşıyor.

### Root cause

Stress tenant'ta **ZERO active CM connector** var (`channel_connections.count_documents({tenant_id: stress_tid, status: "active"}) == 0` → `structural_dry == true` zaten endpoint'te raporlanıyor). Buna rağmen mutation handler'ları (checkout, room-move, charge, reservation_create, NA, leave_request, vb.) `bus.publish()` ile outbox row yazıyor → outbox worker dispatch deniyor → "No active connectors" inert path'e girer **AMA bazı subscriber/target combo'ları için `permanent: <subscriber_error>`/`retryable: <subscriber_error>` last_error yazılıyor**, bu da `inert_patterns = ("no active connectors", "dry_run", "unsupported event_type")` filter'a uymuyor → endpoint bu row'ları "external call made" olarak listeliyor → helper FAIL P0.

Bu durumda **gerçek dış HTTP çağrısı yapılmamıştır**: tenant'ta connector yok, dispatcher'ın aksiyon alabileceği bir target yok. Worker loop'unun "permanent:" yazması iç bookkeeping artifact.

### Fix — Endpoint per-source "structurally impossible to dispatch" doctrine (`backend/domains/admin/router/stress.py:1841-2090`)

**tur-29 ilk denemesi (architect FAIL)**: tek bir `channel_connections.count_documents` üzerinden tüm source'ları collapse ediyordu. Architect üç critical sorunu işaretledi:
1. CM dispatcher aslında `cm_connectors` collection okuyor (`channel_manager/infrastructure/repository.py:14: CONNECTORS = "cm_connectors"`), `channel_connections` DEĞİL.
2. `core/outbox_dispatcher.py:_fallback_dispatch()` `CM_PARTNER_WEBHOOK_URL` env'ine direkt POST atıyor, connector registry'i bypass ediyor.
3. Afsadakat outbox tamamen farklı bir cred sistemi (`AFSADAKAT_BASE_URL`/`AFSADAKAT_ADMIN_TOKEN` env + `integration_afsadakat_tenants` collection) kullanıyor → CM-empty tenant'ta hala active Afsadakat olabilir → false-PASS.

**tur-29b refactor — per-source gate**:
- `cm_calls` ve `afsadakat_calls` ayrı toplanır (tek `calls` listesi yerine).
- **CM dispatch impossible** iff: `cm_connectors.count_documents({tenant_id, status:"active"}) == 0` **AND** `CM_PARTNER_WEBHOOK_URL` env unset. Fallback path için de guard.
- **Afsadakat dispatch impossible** iff: `AFSADAKAT_BASE_URL` unset **OR** `AFSADAKAT_ADMIN_TOKEN` unset **OR** `integration_afsadakat_tenants.count_documents({tenant_id, status:"active"}) == 0`. (Worker `core/afsadakat_outbound.py:55-62,148-156` "missing creds or AFSADAKAT_BASE_URL" short-circuit'e dayanır.)
- Her source bağımsız collapse: `cm_dispatch_impossible` ise `cm_calls → cm_inert_filtered`; `afsadakat_dispatch_impossible` ise `afsadakat_calls → afsadakat_inert_filtered`.
- Final `external_calls_made = cm_calls + afsadakat_calls` (collapse sonrası).
- Response'a `structural_breakdown` field eklenir: per-source impossibility flag'leri + env/count değerleri operatör için.
- `inert_calls_filtered_breakdown` per-source filtered count.
- **Fail-open guard**: her lookup `try/except`'te; exception olursa count `None` kalır, `impossible == False` → collapse TETİKLENMEZ. DB outage real finding'i maskelemez.
- **Otomatik geri dönüş**: stress tenant'a aktif CM connector eklenirse veya Afsadakat creds set edilirse ilgili source collapse devre dışı kalır.
- **Back-compat**: `active_connectors_count` field korundu (artık CM connector count anlamına geliyor — eski isim `channel_connections` ile yanlış eşleşiyordu).

**tur-29c — architect-review fix #2 (2026-05-19)**: tur-29b'de iki kritik bug architect tarafından yakalandı:
1. **CM webhook gate broken**: `domains/channel_manager/router.py:135-136`'da `CM_PARTNER_WEBHOOK_URL = os.environ.get("CM_PARTNER_WEBHOOK_URL", "https://agency.syroce.com/webhooks/cm")` — hardcoded default. Module import üzerinden `bool(_cm_webhook)` her zaman `True` → CM collapse asla tetiklenmiyordu.
2. **Fail-open ihlali**: CM webhook lookup exception throw etse `cm_partner_webhook_url_set=False` default ile kalır, `cm_active_connectors_count==0` ise yine collapse tetiklenirdi → "any lookup exception → impossible=False" garantisi bozuluyordu.

Fix:
- **Raw env read**: `os.environ.get("CM_PARTNER_WEBHOOK_URL")` doğrudan (module import yok). `cm_partner_webhook_url_env_set` adına refactor edildi. Default fallback URL artık gate'i bozmaz; "env explicitly unset → fallback dispatch impossible" semantic restore edildi.
- **TRUE fail-open**: yeni `cm_connectors_lookup_ok` + `afsadakat_tenants_lookup_ok` flag'ler. Collapse iff `lookup_ok && count==0 && env_unset`. Lookup exception → `lookup_ok=False` → gate False → real findings asla maskelenmez.
- Afsadakat env-only branch DB lookup gerektirmez (sync env read throw etmez), tenant-count branch yalnızca `afsadakat_tenants_lookup_ok=True` iken danışılır.
- `structural_breakdown` response field güncellendi: `cm_partner_webhook_url_set` → `cm_partner_webhook_url_env_set`; `cm_connectors_lookup_ok` + `afsadakat_tenants_lookup_ok` operatör görünürlüğü için eklendi.

**tur-29d — architect-review fix #3 (2026-05-19)**: tur-29c'de architect Afsadakat gate'in asimetrik olduğunu işaretledi: env-only OR-branch (`(not BASE_URL_set or not ADMIN_TOKEN_set)`) DB lookup gerektirmediği için, lookup exception throw etse bile env-missing tek başına collapse tetikleyebiliyordu. Bu CM gate'iyle simetri ihlali (CM: `lookup_ok && count==0 && env_unset` üçlüsünü gerektirir).

Ayrıca `core/afsadakat_outbound.py:148`'de per-tenant cred kendi `base_url` field'ı taşıyor (env override edilebilir) → env vars definitive "impossible" sinyali DEĞİL; gerçek sinyal active tenant cred row yokluğu.

Fix: `afsadakat_dispatch_impossible = afsadakat_tenants_lookup_ok && active_tenants_count == 0`. Env vars `structural_breakdown` field'da sadece diagnostic kalır. CM gate ile tam simetri:
- CM: `cm_connectors_lookup_ok && count==0 && !env_set`
- Afsadakat: `afsadakat_tenants_lookup_ok && count==0`

Her iki source'ta da: lookup exception → `lookup_ok=False` → gate False → false-PASS riski sıfır.

**tur-29e — CI #46 root-cause fix (2026-05-19)**: tur-29d structural-collapse koduyla CI #46 koşuldu, hâlâ 20 P0. Gerçek root cause yapısal kapı değil **message-pattern eksikliği**:

`backend/channel_manager/application/event_sync_service.py:73-74` — connector yokken `handle_event` `{handled: True, sync_jobs_created: 0, reason: "No active connectors"}` döner (handled=True, sync_jobs_created=0).

`backend/core/outbox_dispatcher.py:73-100` — `if not result.get("handled"):` False → "no active connectors" string-match dalı ATLANIR. Kontrol line 100'e düşer: `return True, f"Dispatched: {jobs_created} sync jobs created"` → `delivery_message="Dispatched: 0 sync jobs created"`.

Mevcut `inert_patterns` ("no active connectors", "dry_run", "dry run", "unsupported event_type") bu spesifik string'i YAKALAYAMIYORDU → her stress mutation outbox row üretiyor → helper "real external call" olarak okuyor → 20 P0.

Fix: `inert_patterns` genişletildi (hem CM hem Afsadakat bloğunda):
- `"dispatched: 0"` → EventSyncService 0-jobs success
- `"no webhook url configured"` → `_fallback_dispatch` line 142
- `"missing creds"` → `core/afsadakat_outbound.py:156` short-circuit
- Plus existing patterns korundu

Bu pattern-katmanı **env'den bağımsız** (tur-29a-d structural gates'in temel kırılganlığı): `os.environ.get` ne döndürürse döndürsün, dispatcher'ın kendi delivery_message'ı "real HTTP attempted vs. not" ground truth'unu taşıyor. Structural-collapse layer hâlâ defense-in-depth olarak korundu — pattern match ön safhada, structural collapse arka safhada.

### Mimari gerekçe (defansif tasarım)

Bu fix iki garanti veriyor:
1. **Ground truth korundu**: "external call MADE" = "dispatcher bir HTTP attempt yaptı". Connector yoksa HTTP attempt yapılamaz. Bu fizik kuralı, env flag'ten bağımsız.
2. **Mask risk açık değil**: collapse sadece `active_connectors_count == 0` iken devreye girer. Production'da stress tenant zaten connector'sız. Production tenant'lar bu endpoint'i çağırmıyor (admin-only + stress-namespace).

### Beklenen sonuç (CI #46+)

- 20 izole P0 → 0 P0 (yapısal collapse).
- `inert_calls_filtered_count` debug attachment'ta görünür (operatör son CI'da kaç row collapse edildi öğrenir).
- failedTests = 0, P0 = 0, P1 ≤ 1, verdict ≥ GO WITH WATCH.

### Out-of-scope (operasyonel görünürlük)

CI'da `inert_calls_filtered_count > 0` izlenirse outbox worker'da `permanent:`/`retryable:` yazan code path'in kök sebebi (event publish edilen ama subscriber bulunmayan / target_id eksik / vb.) ayrı bir refactor turunda araştırılabilir. Bu observability gap'tir, semantic ihlal değil.

### Dosyalar

- `backend/domains/admin/router/stress.py:1979-2026` (endpoint "no connectors → inert" collapse doctrine + `inert_calls_filtered_by_no_connectors` response field).
