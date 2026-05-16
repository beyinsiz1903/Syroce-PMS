# F8A — Front Office + Folio + Housekeeping Operational Stress — 20260516 (fix narrative)

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`).
> Status: **PRE-RERUN** — this report documents the root-cause analysis and fixes
> applied after CI run #20 reported NO-GO. The next `cd frontend && yarn test:e2e:stress`
> run on CI is expected to verify GO / GO WITH WATCH.

## 1) Yönetici özeti (run #20 NO-GO snapshot)

| Metrik | Değer |
|---|---|
| Toplam test | 53 |
| Passed | 39 |
| Failed | 3 |
| Did not run (skip cascade) | 11 |
| Seed | rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500 |
| Cleanup#1 | deleted_total=5500 |
| Cleanup#2 idempotent | true |
| Pilot drift | 0 |
| Baseline `external_calls_made` | `[]` |
| Final verdict (run #20) | ❌ **NO-GO** — 3 fail (2 external_calls invariant + 1 setup vacant pool) |
| Verdict after fixes (pending re-run) | ⏳ **PENDING CI RE-RUN** — root-cause fixes merged, beklenen GO / GO WITH WATCH |

## 2) Fail edenler — root cause çıkarımı

### Fail #1 — `02-day-turnover.spec.js` › B-post external_calls invariant after force_checkout_batch

- **Symptom**: `Expected true, Received false` from `assertNoExternalCallsPostBatch`.
- **Helper path**: helper `GET /api/admin/stress/external-calls` çağırır; `runtimeOk = calls.length===0 && dry_run_enforced===true && query_errors.length===0`.
- **Backend path**: `/admin/stress/external-calls` (`backend/domains/admin/router/stress.py:432-550`) `sysdb.outbox_events` + `db.integration_afsadakat_outbox` koleksiyonlarını `dispatched_filter` ile sorgular.
- **Root cause**: `dispatched_filter`'da `$or` dalı olarak `{"status": {"$nin": ["pending", None]}}` vardı. Worker'lar event'i "inert" (no active connector / dry_run) olarak işliyor → `status="processed"` + `attempts=0` yazıyor; **gerçek HTTP dispatch yapılmıyor**. Status branch bu satırları yakalıyor, sonra inert-message filter `delivery_message` boş olduğu için "no active connectors" desenini bulamıyor → satır external call sayılıyor → invariant FAIL.
- **"External call MADE" doğru tanımı**: dispatcher gerçekten bir HTTP attempt yaptı → `attempts | attempt_count | retry_count > 0`.
- **Fix** (`backend/domains/admin/router/stress.py:497-503` + `:533-539`): her iki outbox filter'ından `status NOT IN [pending, None]` dalı kaldırıldı. Filter sadece attempt counter'lara bakar. Inert-message filter ikinci kat safety-net olarak duruyor.

### Fail #2 — `03-room-move.spec.js` › Setup: guarantee vacant pool

- **Symptom**: `eligible=0 target_total=50 required_min=30` — setup 1.8m sürüp FAIL.
- **Spec path**: setup `_computeDemand(bookings, 50)` → ilk 50 `checked_in` booking'in `b.room_type` field'ı üzerinden Map oluşturur; sonra `_computeVacantByType(bookings, rooms)` ile cross-check eder; `eligible = Σ min(demand[t], vacant[t])`.
- **Root cause**: Seed factory `bookings_docs`'a **`room_type` yazmıyordu** (`backend/domains/admin/router/stress.py:235-272` — eski sürüm). `b.room_type ?? b.category ?? '__unknown__'` fallback'i hep `__unknown__` döndürüyordu → demand `{__unknown__: 50}`. Rooms ise gerçek `room_type` ile gruplandığı için `vacant.get('__unknown__') = 0` → eligible=0 deterministik.
- **Neden `/api/pms/bookings` enrichment yetmedi?** `pms_bookings.py:440-441`'deki room_type enrichment yalnız cache-warm branch'inde çalışıyor; fetchAllByPrefix'in tetiklediği path enrichment'ı atlıyor → bookings response'unda `room_type` undefined.
- **Fix** (`backend/domains/admin/router/stress.py:248`): seed `bookings_docs` dict'ine `"room_type": room_type` field'ı eklendi (rooms_docs ile aynı `room_type` döngü değişkeni). Pilot tenant'a tek satır etki yok — sadece stress tenant seed payload'una eklendi.
- **Beklenen sonuç**: demand 20 room_type'a yayılır, vacant pool da aynı tiplerde 30+ row gösterir → `eligible >= 30 ≥ required_min` ilk round'da geçer; SETUP_FREE_ROUNDS=4 loop tetiklenmez bile.

### Fail #3 — `04-folio-mass.spec.js` › C2 Total mismatch detector

- **Symptom (literal)**: `folio_reconcile_10 sonrası external_calls invariant ihlal — Expected true, Received false`.
- **Anlamı**: Reconciliation kısmı (sum(charges) vs balance) **PASS** — çift `expect()` var; ikincisi `assertNoExternalCallsPostBatch(... 'folio_reconcile_10' ...)` ve **bu** false döndü. Yani Fail #3 = Fail #1 ile aynı root cause (Kapsam A).
- **Fix**: Aynı `dispatched_filter` değişikliği bunu da kapsar.

## 3) Değişen dosyalar

| Dosya | Değişiklik | Etki |
|---|---|---|
| `backend/domains/admin/router/stress.py:248` | `bookings_docs` ekle: `"room_type": room_type` | 03-room-move setup eligible>=30 |
| `backend/domains/admin/router/stress.py:487-504` | `dispatched_filter` $or'dan `status NOT IN [pending,None]` dalı çıkarıldı; comment block güncellendi | 02-B-post + 04-C2 external_calls invariant PASS |
| `backend/domains/admin/router/stress.py:530-539` | Afsadakat outbox filter'ında aynı değişiklik | Symmetry — her iki koleksiyon için identical kontrat |

Frontend / spec değişmedi (sahte PASS riski yok — assertion gevşetilmedi, sadece backend invariant tanımı doğrultuldu).

## 4) Defans invariant'ları (run #20'de tutuldu)

- `external_calls_made (seed snapshot) = []` ✅
- `gates`: 5/5 true ✅
- `cleanup#1.deleted_total = 5500` ✅
- `cleanup#2.deleted_total = 0` + `idempotent=true` ✅
- `pilot_diff.drift = 0` ✅
- Real external service call (HotelRunner / Exely / payment / SMS / email): 0 ✅

## 5) Targeted re-run plan

Local sandbox stress tenant credential'larına sahip değil; doğrulama CI'da yapılacak:

```
cd frontend && yarn playwright test --config=playwright.stress.config.js \
  -g "B-post|03-room-move|C2 Total"
# sonra full:
cd frontend && yarn test:e2e:stress
```

## 6) Acceptance contract (next run)

- `failedTests = 0`
- `FAIL` adım = 0
- `P0 = 0`, `P1 = 0`
- `pilot_diff.drift = 0`
- `cleanup#2.idempotent = true`
- `external_calls_made = []`
- verdict ≥ **GO WITH WATCH**

## 7) F8B GO/NO-GO kararı

- Backend fix'leri merge edildi; CI re-run beklemede.
- Eğer re-run GO veya GO WITH WATCH dönerse → **F8B'ye GO**.
- Eğer yeniden NO-GO dönerse → tur-8 hardening turu açılmalı; yeni root cause çıkar (örn. dispatcher gerçekten HTTP attempt yapıyor olabilir → dispatcher'da dry_run guard kontrol edilir).

## 8) Artifact pointer'ları

- HTML report: `frontend/playwright-stress-report/` (CI generates per-run)
- Trace: `frontend/test-results-stress/`
- Önceki tur snapshot'ları: `docs/drill_reports/20260514_stress_f8a_*`
- Gotcha güncellemesi: `replit.md` → "F8A Stress" entry (run #20 NO-GO → fix bullet eklendi)
