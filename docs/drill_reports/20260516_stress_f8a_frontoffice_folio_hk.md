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
| Final verdict | ❌ **NO-GO** — run #20 snapshot: 3 fail (2 external_calls invariant + 1 setup vacant pool); fixes tur-7+tur-8 merged, re-run pending |
| Verdict after fixes (pending re-run) | ⏳ **PENDING CI RE-RUN** — root-cause fixes (tur-7 + tur-8) merged, beklenen GO / GO WITH WATCH |
| Tur-8 ek fix | `dry_run_enforced` artık env VEYA "active CM connector=0" yapısal gerçeğinden türetiliyor (deployed backend env propagasyonu bağımlılığı kaldırıldı) |

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
- Eğer yeniden NO-GO dönerse → tur-9 hardening turu açılmalı.

## 8) Tur-8 ek fix — `dry_run_enforced` env coupling (2026-05-16 ikinci pass)

### Verifikasyon
- `.github/workflows/stress.yml:66` workflow env'ine `E2E_EXTERNAL_DRY_RUN: 'true'` set ediyor — **fakat bu CI runner process'i**. Backend `STRESS_E2E_BASE_URL` secret'ında belirtilen **ayrı DigitalOcean deployment**; kendi process env'i DigitalOcean Deployment Secrets üzerinden konfigüre — runner env'i deploy backend'e propagate etmez.
- `rg "E2E_EXTERNAL_DRY_RUN" backend/` → sadece **2 kullanım** (stress.py:127 ve eski 563). Flag hiçbir yerde dispatcher davranışını gerçek olarak kapı tutmuyor; pure self-report.
- Helper `runtimeOk = calls.length===0 && dry_run_enforced===true && query_errors.length===0` (stress-helpers.js:129). `dry_run_enforced=false` olunca calls=[] olsa bile FAIL.
- Sonuç: stress backend'i `E2E_EXTERNAL_DRY_RUN=true` env'i ile başlatılmadıkça helper SAHTE FAIL veriyor; gerçek invariant (outbox boş + worker dispatch yok) tutarken bile.

### Fix
- `backend/domains/admin/router/stress.py:563-610` (endpoint return bloğu): `dry_run_enforced = env_dry OR structural_dry`. `structural_dry = (db.channel_connections.count_documents({tenant_id:stress_tid, status:"active"}) == 0)`. Yapısal kanıt: stress tenant'ında **aktif CM connector yok** → EventSyncService "No active connectors" döner → dispatcher hiçbir HTTP attempt yapamaz. Bu, env bayrağıyla aynı garantiyi sağlar ama deployment env propagasyonuna bağımlı değildir.
- Response'a ek debug alanları: `dry_run_source` (`env|structural_no_active_connectors|env_and_structural|none`), `dry_run_env_flag`, `dry_run_structural`, `active_connectors_count`. Geri uyumlu — eski `dry_run_enforced` alanı korundu, anlamı genişledi.
- `frontend/e2e-stress/fixtures/stress-helpers.js:136-158`: `dry_run_enforced=false` olunca tam response body + runner env snapshot Playwright attachment olarak yazılır (`external-calls-debug-<batchName>.json`). Future regression için root-cause data baseline (re-run gerektirmez).

### Assertion gevşetilmedi mi?
- Hayır. `external_calls_made.length===0` (ground truth) hâlâ zorunlu.
- `query_errors.length===0` (DB sorgu hatası yok) hâlâ zorunlu.
- `dry_run_enforced===true` hâlâ zorunlu — fakat şimdi **doğrulanabilir yapısal gerçeği** kabul ediyor; sadece "biri env değişkeni set etmiş" self-report'una bağımlı değil. Pilot tenant'ında active connector varsa (production-like) bu structural branch true dönmez → invariant koruması bozulmaz.

### Etkilenen testler
- 02-day-turnover B-post external_calls invariant → PASS (eski fail #1)
- 04-folio-mass C2 external_calls invariant → PASS (eski fail #3)
- Diğer post-batch invariant çağrıları (02 D-post, 04 A/B/C, 08 OOO, vs.) → aynı kontratta, otomatik fayda

### Acceptance (next CI run)
- failedTests=0 · FAIL adım=0 · P0=0 · P1=0
- `external_calls_made=[]` + `dry_run_enforced=true` (source=`structural_no_active_connectors` beklenen)
- pilot_diff.drift=0 · cleanup#2.idempotent=true
- verdict ≥ **GO WITH WATCH**

### Değişen dosyalar (ek)
| Dosya | Değişiklik | Etki |
|---|---|---|
| `backend/domains/admin/router/stress.py:563-610` | `dry_run_enforced` env OR structural; debug alanları eklendi | env propagasyon bağımlılığı kaldırıldı |
| `frontend/e2e-stress/fixtures/stress-helpers.js:133-158` | `dry_run_enforced=false` durumunda tam response body + runner env attachment | Future root-cause baseline |

## 8) Artifact pointer'ları

- HTML report: `frontend/playwright-stress-report/` (CI generates per-run)
- Trace: `frontend/test-results-stress/`
- Önceki tur snapshot'ları: `docs/drill_reports/20260514_stress_f8a_*`
- Gotcha güncellemesi: `digitalocean.md` → "F8A Stress" entry (run #20 NO-GO → fix bullet eklendi)
