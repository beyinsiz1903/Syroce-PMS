# F8AF — RMS Revenue Deep Stress — Spec Written (2026-05-24)

> **Status:** Spec written + `node --check` PASS + `STRESS_COLLECTIONS`
> orphan-scrub anchors added. Full-suite green verification next CI run
> (F8X–F8AA + F8AB + F8AC + F8AF birlikte baseline 69 → 70 spec). Bu
> rapor "spec-written" milestone'unu kaydeder; resmi GREEN baseline
> raporu CI run sonrası ayrıca eklenecek.

## 1) Run künyesi

| Alan | Değer |
|---|---|
| Tarih | 2026-05-24 |
| Faz | F8AF — RMS Revenue Deep Stress |
| Module | `revenue_management` |
| Spec dosyası | `frontend/e2e-stress/specs/98-rms-revenue-deep.spec.js` |
| Test sayısı | 8 (Setup + A read-only + B policy/forecast + C autopilot pipeline + D displacement + E hurdle CRUD + F ai-pricing dry-run + G IDOR + Z cleanup) |
| Backend değişikliği | `backend/domains/admin/router/stress.py` `STRESS_COLLECTIONS` += `revenue_autopilot_policies`, `revenue_approval_queue`, `revenue_apply_results`, `displacement_analyses`, `demand_forecasts`, `hurdle_rates` (orphan-scrub forward-compat anchors) |
| Baseline | 69 → **70 spec** (full-suite verification pending) |

## 2) Kapsam

### Setup) Pilot baseline + module probe + force advisory mode
`/api/revenue-autopilot/dashboard|policy|queue` probe; herhangi biri 403/404
→ `moduleBlocked=true` + P2 + A..G skip. Orijinal policy snapshot alınır
(`originalMode`/`originalPolicy` module-level state); ardından PUT ile
`mode=advisory` zorlanır — full_auto modunda arka plan gerçek `_apply_price`
+ kanal push tetikleyebilir; advisory garanti dry-run + queue rejimi.
Cleanup `Z3`'te orijinal mode geri yazılır (best-effort).

Forbidden literal source-scan guard: `FORBIDDEN_AI_AUTOPILOT_RUN`
(`/api/autopilot/run-cycle`) + `FORBIDDEN_AI_AUTOPILOT_SETMODE`
(`/api/autopilot/set-mode`) spec source'unda literal SUBSTRING olarak
geçmemeli; `assertEndpointNeverCalled` ile doğrulanır (F8O doctrine).

### A) Read-only probes
`/api/revenue-autopilot/dashboard`, `/queue?limit=10`, `/summary`,
`/api/displacement/market-overview?days=7`, `/api/displacement/history`,
`/api/hurdle-rates/`, `/api/rms/demand-forecast?days=7` — non-2xx = P2
informational (lifecycle invariant intact).

### B) Policy update + demand-forecast POST
- B1: PUT `/api/revenue-autopilot/policy` `{mode:'advisory',
  confidence_threshold_auto:0.99, confidence_threshold_queue:0.30,
  max_price_change_pct:25.0, blackout_dates:[today, +1d],
  protected_room_types:['Penthouse']}` → 2xx zorunlu. GET ile
  `mode==advisory` doğrulanır (regression on `update_policy` allowed-field
  filter); mismatch = P1.
- B2: POST `/api/rms/demand-forecast` `{start_date:+7d, end_date:+9d}`
  (3-day window — DB yükünü sınırla); 2xx zorunlu, 403/404 = P2.

### C) Autopilot pipeline (process / approve / reject)
- C1: POST `/process` `{room_type:'<prefix>_Standard', target_date:+14d,
  current_price:100, recommended_price:112, confidence:0.55}` (under
  max_price_change_pct=25, confidence > queue_threshold=0.30, mode=advisory)
  → expected `action=queued`. **SAFETY: action=='auto_applied' = P0**
  (advisory mode kontrolü kırılmış; rate publish queue'suz tetiklenmiş).
- C2: Process + approve — yeni rec ile pending item üret, sonra
  POST `/queue/{item_id}/approve` → 2xx zorunlu.
- C3: Process + reject — POST `/queue/{item_id}/reject` `{reason:'…'}`
  → 2xx zorunlu.

### D) Displacement (analyze / compare / save)
- analyze: POST `/api/displacement/analyze` `{check_in:+20d,
  check_out:+22d, rooms_requested:5, proposed_rate:120, group_name:'<prefix>_GroupD',
  ancillary_per_room:15, commission_pct:5}` → 2xx.
- compare: POST `/api/displacement/compare` 3 senaryo (low/mid/high).
- save: POST `/api/displacement/save` → kayıt `displacement_analyses`
  koleksiyonuna işlenir (orphan-scrub anchor mevcut).

### E) Hurdle rates CRUD
- POST `/api/hurdle-rates/` `{name:'<prefix>_HurdleE', date_from:+30d,
  date_to:+45d, min_rate:80, currency:'TRY', active:true}` → **201** zorunlu;
  id `createdHurdleIds`'a push.
- PATCH `/api/hurdle-rates/{id}` `{min_rate:100}` → 2xx zorunlu.
- GET `/check?date=+31d&proposed_rate=150` → `allowed=true` zorunlu
  (proposed >= min_rate); false dönerse P1.
- GET `/check?date=+31d&proposed_rate=50` → `allowed=false` zorunlu
  (proposed < min_rate); true dönerse P1.

### F) AI pricing auto-publish dry-run
POST `/api/rms/ai-pricing/auto-publish-rates?start_date=+50d&end_date=+52d&strategy=balanced`
→ 2xx + response shape sanity (`rates_published` not null).
**Critical:** Bu endpoint historik olarak channel push / CM outbox
tetikleyebilir (`backend/domains/revenue/pricing_router/ai_pricing.py`
L287-357). Batch sonu `assertNoExternalCallsPostBatch` delta=0 ZORUNLU —
gerçek HTTP çağrısı tetiklenirse invariant patlar.

### G) Cross-tenant IDOR — stress_token → pilot_id (F8X doctrine)
- **G1 (hurdle):** pilot_token ile `/api/hurdle-rates/` harvest →
  pilot_hurdle_id varsa:
  - stress_token PATCH `/api/hurdle-rates/{pilot_id}` `{min_rate:1.0}`
    → ≥400 hard-asserted. 2xx = **P0** + bug fix direktif
    (`backend/domains/revenue/hurdle_router.py update_hurdle` zaten
    `tenant_id` filter + `matched_count==0 → 404` pattern uyguluyor;
    eğer 2xx dönerse regression).
  - stress_token DELETE `/api/hurdle-rates/{pilot_id}` → ≥400.
    Pilot boş ise SKIP + P2 informational (vector not exercised).
- **G2 (autopilot queue):** pilot_token ile `/api/revenue-autopilot/queue?status=pending&limit=5`
  harvest → pilot_item_id varsa:
  - stress_token POST `/queue/{pilot_item_id}/approve` → ≥400 hard-asserted.
  - **F8X doctrine flag:** Backend service `approve_item` şu an
    `find_one({"id": item_id, "tenant_id": tenant_id, "status": PENDING})`
    none dönerse `{"success": False, "error": "..."}` ile **HTTP 200**
    döner (`backend/modules/revenue_autopilot/service.py:230-231`). Bu
    silent 200 no-op F8X precedent'inde (accounting/invoices) **gerçek
    regression risk** olarak işaretlendi; spec ≥400 hard-assert ediyor —
    pilot queue dolu çıkarsa test FAIL → service.py'ya
    `if not item: raise HTTPException(404, "Item not found or not pending")`
    fix uygulanır (F8X-pattern, hem `approve_item` hem `reject_item` hem
    `rollback_item`'da paralel düzeltme).
- **G3 (bogus-id):** her zaman koşar (pilot harvest'a bağlı değil) —
  `00000000-0000-0000-0000-000000000000` UUID ile:
  - POST `/queue/{bogus}/approve` → ≥400 (yukarıdaki silent 200 no-op
    bu vektörle de yakalanır — pilot'a bağımsız).
  - PATCH/DELETE `/api/hurdle-rates/{bogus}` → ≥400 (hurdle_router
    zaten 404 raise ediyor; defansif).

### Z) Cleanup + restore policy
- Z1: `createdHurdleIds` üzerinde DELETE round-trip; second pass 404
  zorunlu, non-404 = P1 (cleanup contract broken).
- Z2: `createdQueueItemIds` (pending olanlar) için reject POST;
  delete endpoint yok — pending olmayan item'lar `success:false` döner
  (no-op idempotent).
- Z3: orijinal policy mode geri yazılır (best-effort, snapshot yoksa SKIP).
- Final: `assertNoExternalCallsPostBatch` + `assertPilotDriftZero` her
  test'te `try/finally` bloğunda.

## 3) Mutlak invariant gates

| Gate | Beklenen | Spec'te enforce |
|---|---|---|
| `failedTests == 0` | ✅ | `expect().toBeGreaterThanOrEqual(200|400)` hard-asserts |
| `FAIL adım == 0` | ✅ | `rec(testInfo, {…, status: 'PASS'/'FAIL'})` annotation |
| `P0 == 0` | ✅ | cross-tenant IDOR + advisory→auto_applied + silent 200 no-op = P0 + ≥400 hard-assert |
| `P1 == 0` | ✅ | policy mode persist gap + hurdle check inverse + cleanup non-idempotent = P1 |
| `external_calls == []` | ✅ | her test finally'da `assertNoExternalCallsPostBatch` (AI pricing batch dahil) |
| `pilot_drift == 0` | ✅ | her test finally'da `assertPilotDriftZero` |
| Cleanup idempotent | ✅ | Z1 second-pass DELETE → 404 zorunlu |
| Forbidden literal | ✅ | `FORBIDDEN_AI_AUTOPILOT_RUN`/`SETMODE` source-scan PASS |

## 4) Doktrine ve guard'lar

- **Module-blocked pattern**: dashboard/policy/queue probe herhangi biri
  403/404 → `moduleBlocked=true` + P2 informational + A..G `test.skip`;
  Z cleanup + pilot_drift bağımsız çalışır (F8AB/F8AC mirror).
- **Advisory mode enforcement**: Setup'ta force advisory; C1 `auto_applied`
  dönerse P0 (mode kontrolü kırık). Z3 orijinal mode geri yazılır →
  prod-like state preserved.
- **F8X doctrine (silent 200 no-op)**: G2 + G3 yolu approve/reject/rollback
  endpoint'lerinin not-found durumunda `success:false`+200 dönmesini
  regression-risk olarak işaretler. Gerçek IDOR mutation yok (`find_one`
  tenant_id ile guard ediyor) ama HTTP code semantik regression. CI yeşil
  olması için backend fix gerekirse `service.py approve_item/reject_item/
  rollback_item`'a `if not item: raise HTTPException(404, ...)` eklenir
  (F8X invoices/accounting fix pattern'i).
- **AI pricing publish safety**: F batch sonunda dispatcher delta=0
  ZORUNLU. `auto_publish_rates_based_on_forecast` historik kanal push
  tetikleyebilir — invariant yakalar.
- **Stress collections**: `revenue_autopilot_policies`,
  `revenue_approval_queue`, `revenue_apply_results`, `displacement_analyses`,
  `demand_forecasts`, `hurdle_rates` orphan-scrub anchor olarak eklendi
  (mevcut router'lar `stress_seed` tag pass-through yapmadığı için no-op;
  forward-compat: gelecekteki tag'li seed insert'leri unified cleanup
  loop yakalar).

## 5) Sonraki adımlar

1. Full-suite CI run (Full Operational Stress Suite + F8X..F8AF).
2. G2 pilot harvest dolu çıkar ve approve 200 dönerse → backend
   `service.py` F8X-pattern fix uygulanır, republish, CI re-run.
3. Green run sonrası `docs/drill_reports/` altına resmi GREEN baseline
   raporu (70 spec) eklenecek.
4. Roadmap "Latest verified baseline" satırı 69 → 70 olarak güncellenecek.

## 6) İlgili dosyalar

- `frontend/e2e-stress/specs/98-rms-revenue-deep.spec.js` — yeni spec
- `backend/domains/admin/router/stress.py` — `STRESS_COLLECTIONS` += revenue
- `backend/routers/revenue_autopilot_v2.py` — autopilot endpoint surface
- `backend/modules/revenue_autopilot/service.py` — F8X fix kandidatı
  (`approve_item`/`reject_item`/`rollback_item` silent 200 no-op)
- `backend/routers/displacement_analysis.py` — displacement surface
- `backend/domains/revenue/hurdle_router.py` — hurdle CRUD (F8X-clean)
- `backend/domains/revenue/rms_router/demand_forecast.py` — forecast surface
- `backend/domains/revenue/pricing_router/ai_pricing.py` — AI pricing
  auto-publish surface
- `docs/STRESS_TEST_ROADMAP.md` — F8AF baseline note
- `docs/GOTCHAS.md` / `replit.md` — F8 Stress Test Series altında F8AF satırı
- `frontend/e2e-stress/fixtures/stress-helpers.js` — reuse-only
- `frontend/e2e-stress/fixtures/stress-context.js` — reuse-only
