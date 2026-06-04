# Stress Test Roadmap (F8 Serisi)

**Hedef:** Tüm PMS modül yüzeylerini sırayla GitHub Actions stress CI'ya
sokmak — pilot tenant'a mutation yok, gerçek dış servis çağrısı yok,
external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH.

## F9 — Full App Coverage Closure Sprint (2026-05-27, IN PROGRESS)

**Tetik:** `docs/TEST_COVERAGE_GAP_MAP_20260527.md` — sayfa bazında %40 ZERO, endpoint bazında %57 ZERO. Business rule: hiçbir sayfa/modül tamamen testsiz kalmamalı.

| Faz | Durum | Teslim |
|---|:---:|---|
| **F9A** Frontend zero-page smoke matrix | ✅ DONE (2026-05-27) | `frontend/e2e-smoke/routes.js`'e 31 yeni route eklendi (`critical: false`), `fixtures.js` `inspectPageContent`'a PII/token leak scan eklendi (JWT, kart PAN, CVV, bearer/api-key). Syntax OK. Smoke run deploy env'de tetiklenmesi gerekli — bu environment'tan çalıştırılamaz |
| **F9B** Backend zero-router probe spec | ✅ DONE (2026-05-27) | `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js` — **51 router modülü** için parametric probe (anon→401/403 enforcement, auth→non-500 gate, list-shape sanity, doctrine-safe GET-only). Module-blocked → REVIEW, endpoint absent → REVIEW (PASS değil). 5xx veya anonymous bypass → P1 hard fail. Syntax OK. Deploy env'de koşulması bekliyor |
| **F9C** 7 dedicated deep stress specs | ✅ FILES DONE / ⏳ TARGETED 7/7 — 4 GO, 3 NO-GO→**RESOLVED** (NO-GO 2026-05-27; 3 P1 kapatıldı + **2026-06-04 doğrulandı**) | 7/7 spec mevcut + `node --check` PASS + per-spec architect review kayıtlı (Task #40-#46, #41 Round-3 PASS). Targeted pilot CI drill 7/7 koşuldu (Task #53 BEO, #47 Sales, #82 kalan 5). **Honest verdict per drill (`docs/drill_reports/20260527_stress_98_*_verify.md`):** GO → `98_messaging_template`. GO WITH WATCH → `98_marketplace_deep`, `98_fnb_beo_generator`, `98_sales_lifecycle` (f9c tag). **NO-GO (real backend P1 surfaced)** → `98_maintenance_workorder` (POST `/api/maintenance/work-orders` → 500 ASGI exception on insert path), `98_mobile_staff` (GET `/api/notifications/preferences` → 500), `98_mobile_cashier` (PIN brute-force gate — 7 wrong creds = 7×401, no 429 throttle on financial gate). Targeted-run gate met (specs really executed against pilot, no fake PASS), but suite cannot be promoted into a green baseline until the 3 P1s are fixed. Detay: `docs/DAILY_CHANGE_REVIEW_20260527.md` §3. **3 P1 RESOLVED + DOĞRULANDI (2026-06-04, targeted; agent dispatch YOK):** (1) maintenance work-orders 500 → `backend/tests/test_maintenance_workorder_create.py` 3 passed (insert path onarıldı); (2) mobile_cashier PIN brute-force no-429 → Task-51 `CASHIER_HANDOVER_USER`/`_IP` always_on iki-katmanlı sliding-window (bcrypt-öncesi, `DISABLE_AUTH_THROTTLE`'a bağışık) + `test_cashier_handover_throttle.py` 5 passed; (3) mobile_staff `GET /api/notifications/preferences` 500 → handler kayıt yoksa default-pref döner, canlı read-only probe **HTTP 200**. Kök-neden backend P1'leri kapalı; F9C deep spec'lerin yeşil baseline'a PROMOTE'u hâlâ **operatör full-stress dispatch'i** bekliyor (agent full stress dispatch EDEMEZ). post_f9c pack (2026-05-27) maintenance+mobile_staff'ı zaten GO'ya çekmişti; cashier o gün NO-GO'ydu, sonra Task-51 ile kapatıldı. |
| **F9D-FOLIO** Finance folio & guest-purchase deep stress spec | ✅ DONE (2026-05-27) | `frontend/e2e-stress/specs/99-finance-folio-surface.spec.js` — module `finance_folio`. Kapsam: GET `/api/folio/list` + `/api/folio/{id}` read smoke, POST `/api/folio/{id}/charge` + `/api/folio/{id}/payment` X-Idempotency-Key replay (aynı key → aynı id; farklı id = P1 finansal çift-post), POST `/api/folio/{id}/void-charge/{cid}` + `/api/folio/{id}/payment/{pid}/void` (refund/void lifecycle), guest endpoint probes `/api/guest/purchase-upsell/{bid}` (staff JWT → 4xx zorunlu; 2xx = P1 elevation-of-privilege) + `/api/guest/purchased-upsells/{bid}` (own-tenant 200, pilot booking_id → items=0 ya da P0 cross-tenant leak), **P0 cross-tenant IDOR**: pilot_folio_id harvest → stress_token detail/charge/payment/close hep ≥400 hard-asserted (2xx = P0 disclosure+tampering), anonymous headerless `/api/folio/list` → 401/403 (P1 not blocked), bogus folio id mutations → 4xx. Invariants: `external_calls=[]`, `pilot_drift=0`. Teardown: spec-side void primary, unified cleanup script `folio_charges`/`payments` orphan-scrub secondary. Syntax OK |
| **F9D** Targeted runs (deploy env) | 🟡 READY — awaiting CI dispatch | Local'den koşulamaz. Task #59: `stress.yml` workflow_dispatch artık `spec_pattern` input destekliyor; F9D koşusu için Actions → "Full Stress Suite (one-shot)" → Run workflow ile `spec_pattern=specs/99-finance-folio-surface.spec.js` + `report_tag=f9d_finance_folio` geçilir. Sonuç drill report `docs/drill_reports/YYYYMMDD_stress_f9d_finance_folio.md` artifact'tan indirilir; failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0 doğrulanır. |
| **F9E** Full suite re-run | ⛔ BLOCKED on F9D | Hedef: 85+ spec → drill report `20260527_f9_full_app_coverage_closure.md` |
| **F9F** Doc updates | 🔄 PARTIAL | Roadmap (bu blok), gap map ZERO→PARTIAL transitions, pilot trust (sadece CI green sonrası) |

**Doktrin kuralları F9 boyunca aynen geçerli:** fake PASS yok, skip-as-pass yok, P2/REVIEW downgrade yok, `external_calls=[]`, `pilot_drift=0`, cleanup idempotent. Module-blocked → P2 REVIEW (PASS değil). Destructive POST yok (dry-run + stress-prefixed seed dışında).

---

## Closing note (2026-05-26 baseline stabilization)

**2026-05-26:** Run #143 official 84-spec GO WITH WATCH baseline stabilized. Stale T001–T006 plan retired. P2/REVIEW triage moved to §11 pre-pilot decision matrix (`docs/STRESS_P2_REVIEW_TRIAGE_20260526.md`). Sentry worker noise reduction completed with `TransientFailureTracker` across 11 workers, architect Round-2 PASS, commit `6f48e71`. **Bu noktadan sonra yeni faz ayrı başlık altında açılacak: Pilot Onboarding Pack · MUST CLOSE PC1–PC4 Sprint · Sales/Investor Readiness Pack.**

---

## Latest verified baseline (2026-05-30) ✅ GREEN — 702 test, Run #167

| Alan | Değer |
|---|---|
| Date | 2026-05-30 |
| Workflow | GitHub Actions — Full Stress Suite (one-shot) |
| Run | **#167** |
| Run URL | https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26687012176 |
| Run ID / Job ID | 26687012176 / 78656853578 |
| Trigger | one-shot dispatch |
| Branch | `main` |
| Commit SHA | `0b99607fe3a64a7ada660d1f1bcb8607bd47f5dd` |
| Status | Success |
| Artifacts | 2 (stress-drill-report ID 7309449913, digest sha256:7a4d424aac978ba3adeed1851d911545196e0fd46c773616b176f20960e3a46d · playwright-stress-report ID 7309449854, digest sha256:288544edb3ada9c2a001559a2aadc4fae1c4c198b35a8024f1fffd1107ade622) |
| Toplam test | **702** |
| failedTests | **0** |
| Adım PASS / FAIL / REVIEW / SKIP | **1379 / 0 / 48 / 44** |
| P0 / P1 / P2 / P3 | **0 / 0 / 58 / 1** |
| `external_calls_made` | `[]` ✓ |
| `pilot_drift` | 0 ✓ |
| Cleanup idempotent | ✅ (cleanup#2 idempotent=true) |
| Final verdict | ✅ **GO WITH WATCH** — P2=58 REVIEW=48 SKIP=44 P3=1 (downgrade YOK; doktrin ≥ GO WITH WATCH karşılanıyor) |
| Validates | ai_pricing recommend-rates deterministik 500 fix (pilot kirli base_price). FAIL 1→0, ai_pricing 20/1→21/0. Detay: `docs/drill_reports/20260530_ai_pricing_recommend_rates_500_fix.md`. |
| Drill report | `docs/drill_reports/20260530_stress_full_stress_suite_GREEN_702test_run167.md` |

**NOT — kapsam:** Bu baseline **web/backend full stress suite** içindir.
**/100 uygulama kapsamı DEĞİLDİR.** Mobile (F10) coverage ayrı ve açık
(doğrulanmadı); `docs/TEST_COVERAGE_SCORECARD_100.md` merkezi referanstır.

### Historical reference — Run #162 (2026-05-29) ✅ GREEN — 702 test

| Alan | Değer |
|---|---|
| Date | 2026-05-29 |
| Run | **#162** (superseded by #167 on 2026-05-30) |
| Run URL | https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26653464472 |
| Run ID / Job ID | 26653464472 / 78557501168 |
| Commit SHA | `bde7662744c9b94a5c9294fa778202d813319dfc` |
| Duration | 3576.2s (~59m 36s) |
| Toplam test | 702 |
| failedTests | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1316 / 0 / 46 / 61 |
| P0 / P1 / P2 / P3 | 0 / 0 / 60 / 1 |
| `external_calls_made` | `[]` |
| `pilot_drift` | 0 |
| Cleanup idempotent | ✅ (cleanup#1=7756 → cleanup#2=0) |
| Artifacts | stress-drill-report ID 7298692917, digest sha256:ca8a84b03c07972ad70024284082f5f93d69f779ea441d21103dd24e6d266d28 · playwright-stress-report ID 7298692578, digest sha256:89f2e67d44099ba6ce603c1c5c4fd92bdee33966e7bd3b8c84b1e59c7939be07 |
| Final verdict | ✅ GO WITH WATCH |
| Drill report | `docs/drill_reports/20260529_stress_full_stress_suite_GREEN_702test.md` |

### Historical reference — Run #161 (2026-05-29) ✅ GREEN — 702 test

| Alan | Değer |
|---|---|
| Date | 2026-05-29 |
| Run | **#161** (superseded by #162 on 2026-05-29) |
| Run URL | https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26641150604 |
| Run ID / Job ID | 26641150604 / 78514272098 |
| Commit SHA | `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67` |
| Duration | 3441.6s (~57m 22s) |
| Toplam test | 702 |
| failedTests | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1314 / 0 / 48 / 61 |
| P0 / P1 / P2 / P3 | 0 / 0 / 65 / 1 |
| `external_calls_made` | `[]` |
| `pilot_drift` | 0 |
| Cleanup idempotent | ✅ (cleanup#1=7756 → cleanup#2=0) |
| Artifacts | stress-drill-report ID 7293609890 · playwright-stress-report ID 7293609632 |
| Final verdict | ✅ GO WITH WATCH |
| Drill report | comparison block içinde korunmuştur (`docs/drill_reports/20260529_stress_full_stress_suite_GREEN_702test.md`) |

### Historical reference (older) — Run #159 (2026-05-28) ✅ GREEN — 702 test

| Alan | Değer |
|---|---|
| Date | 2026-05-28 |
| Run | **#159** (superseded by #161 on 2026-05-29) |
| Run URL | https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26601324830 |
| Run ID / Job ID | 26601324830 / 78385405937 |
| Commit SHA | `e23a4ec603cc32984b741d77d67d57a0abba698b` |
| Duration | 3623.6s (~60m 24s) |
| Toplam test | 702 |
| failedTests | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1314 / 0 / 48 / 61 |
| P0 / P1 / P2 / P3 | 0 / 0 / 65 / 1 |
| `external_calls_made` | `[]` |
| `pilot_drift` | 0 |
| Cleanup idempotent | ✅ (cleanup#1=7756 → cleanup#2=0) |
| Final verdict | ✅ GO WITH WATCH |
| Drill report | `docs/drill_reports/20260528_stress_full_stress_suite_GREEN_702test.md` |

### Historical reference (older) — Run #143 (2026-05-26) ✅ GREEN — 84 spec

| Alan | Değer |
|---|---|
| Date | 2026-05-26 |
| Run | **#143** (superseded by #159 on 2026-05-28, then #161 on 2026-05-29) |
| Commit SHA | `3b3891d` |
| Duration | 47m 55s |
| Spec count | 84 |
| Toplam test | 556 |
| failedTests | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1087 / 0 / 46 / 73 |
| P0 / P1 / P2 / P3 | 0 / 0 / 60 / 1 |
| `external_calls_made` | `[]` |
| `pilot_drift` | 0 (baseline=30, after=30) |
| Cleanup idempotent | ✅ (cleanup#1=7734 → cleanup#2=0) |
| Seed prefix | `E2E_STRESS_F7_1779861740675_` |
| Final verdict | ✅ GO WITH WATCH |
| Drill report | `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` |

**Faz kapsamı (bu baseline'a giren):** F8A + F8B + F8C + F8D (v2 + v3
HR extension) + F8E + F8F..F8O + F8R + F8S + F8U + F8V + F8W + **F8X +
F8Y + F8Z + F8AA + F8AB + F8AC + F8AD + F8AE + F8AF + F8AG + F8AH +
F8Z.2 + F8M-v2 + POS/Spa derinleştirmeleri**.

**Eklenen 16 spec (68 → 84):** `98-efatura-earsiv-dryrun`,
`65-identity-reporting-kbs-jandarma-dryrun`,
`98-payment-pos-reconciliation-dryrun`,
`66-kvkk-retention-deletion-anonymization`,
`98-spa-wellness-operational`, `98-konaklama-vergisi-dryrun`,
`98-rms-revenue-deep`, `98-pos-kds-inventory`,
`41B-b2b-subrouter-matrix`, `98-golf-operational`,
`98-vcc-pci-compliance`, `98C-twofa-totp-lifecycle`,
`98-ops-surface-smoke`, `99-pos-extensions`,
`98-pos-deep-lifecycle`, `99-full-24h-hotel-simulation`.

**F8AH iki-tur kapatma (5 finding):** Tur 1 commit `94514e6` — 4 P1
(konaklama amount/nights overflow → Pydantic `le=1e9/3650` clamp,
KDS terminal-state → 409 guard, KDS idempotency → Mongo unique index
+ 503 fail-closed). Tur 2 commits `147266d4` + `67374954` + `8f7f77b6` —
P0 TWOFA brute-force throttle: Mongo-backed cross-instance throttle
(`backend/security/auth_throttle.py` `_ensure_mongo_throttle_indexes`
+ `_check_mongo`, `always_on=True` routing) + per-user_id layered
throttle (JWT-trusted `user_id` claim, IP rotation immune,
`consumed_jtis` insert ÖNCESI placement → no DB write amplification
under brute force). Local smoke: 17 verify → 1-15=401, 16-17=429 ✓.
Architect review PASS her iki turda. Residual non-blocking: Mongo
outage `always_on` throttles için fail-open (availability politikası
ile uyumlu, strict-mode + alerting backlog).

**Drill report:** [`docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md`](./drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md)

**Coverage gap raporu:** [`docs/STRESS_COVERAGE_GAP_REPORT_20260526.md`](./STRESS_COVERAGE_GAP_REPORT_20260526.md)

**Delta — 2026-05-27 (Task #85):** Suite **+1 spec** — `98D-peer-login-throttle.spec.js`.
Live probe for the Task-55 per-IP + per-account `always_on` SlidingWindow
throttles wired into `POST /api/agency-portal/auth/login` and
`POST /api/supplies-market/vendor/login`. Pairs with F8AH `98C-twofa-totp-lifecycle`
as the second `always_on` brute-force coverage spec. Asserts: agency surface
combined drain + per-account boundary (10 wrong → successful login drains via
router `AGENCY_LOGIN_*.reset()` → 11 wrong post-drain, 11th = 429 with
`Retry-After`), vendor surface per-IP boundary (21 distinct emails, 21st = 429
with `Retry-After`). Module-blocked semantics: `E2E_STRESS_ADMIN_*` missing
or stress admin non-super_admin (403) → SKIP + P2; endpoint 404/0 → SKIP +
P2; 5xx on bogus credentials → P1 (DoS sentinel). Invariants:
`external_calls=[]`, `pilot_drift=0`. Backend coverage unchanged —
`backend/tests/test_peer_login_throttle.py` continues to exercise the
throttle module directly. Syntax OK (`node --check`); live verification
deferred to next full-suite CI dispatch.

**Delta — 2026-05-27 (Task #53):** Suite **84 → 85 spec**. F9C `98-fnb-beo-generator.spec.js`
(Task #44'te yazılmış, syntax-only kabul edilmişti) live backend'e karşı bir kez
koşturuldu — verdict **GO WITH WATCH** (failedTests=0, P0=P1=0, P2=1 informational,
REVIEW=2, SKIP=8). Setup probe `GET /api/mice/events` → 403 `ENTITLEMENT_DENIED`
(stress tenant'ta `modules.mice` enable değil — `mice_events` ile aynı baseline
davranışı, "RBAC by design" doctrine'i altında). Module-blocked doctrine devreye
girdi: A–H lifecycle SKIP, J/K security probes PASS (IDOR 404, headerless 403),
M (external_calls=[]) PASS, N (pilot drift=0 + BEO prefix scan) PASS. Cleanup
ledger boş (created=0 → cancel hedefi yok). Drill report:
[`docs/drill_reports/20260527_stress_98_fnb_beo_generator_verify.md`](./drill_reports/20260527_stress_98_fnb_beo_generator_verify.md).

---

## Historical reference — 2026-05-24 baseline (68 spec, commit `ee7573b3`)

> **F8X–F8AA Local Compliance & Money Safety Pack** spec'leri yazıldı
> (2026-05-24, bu commit) — 4 yeni spec (98-efatura, 65-identity, 98-payment,
> 66-kvkk). Verified baseline rakamları **F8R–F8W dahil 68 spec** içindir;
> F8X–F8AA full-suite verification roadmap'in bir sonraki adımıdır.
>
> **F8AB Spa & Wellness Operational Stress** spec'i de yazıldı
> (2026-05-24, bu commit) — `frontend/e2e-stress/specs/98-spa-wellness-operational.spec.js`.
> Suite baseline 68 → **69 spec** (F8X–F8AA + F8AB full-suite verification
> bir sonraki adım). Spec doctrine: catalog smoke + appointment lifecycle
> (scheduled→in_progress→completed + no_show + cancelled) + atomic conflict
> guard (terapist/oda overlap → 409) + auto-pick + waitlist CRUD/promote +
> P0 cross-tenant IDOR (pilot bearer'ı stress-created appt/waitlist mutate
> edemez) + Idempotency-Key replay (aynı tuple → 409). Folio posting safety:
> `charge_to_room=True + reservation_id=null` short-circuit ile Xchange
> publish ASLA tetiklenmez; external_calls invariant batch sonunda
> doğrulanır. `STRESS_COLLECTIONS` listesine `spa_appointments`,
> `spa_waitlist`, `spa_services`, `spa_therapists`, `spa_rooms`, `spa_locks`
> eklendi (orphan-scrub safety net; spec-side teardown DELETE primary
> path'tir).
>
> **F8Z.2 POS KDS Print + F&B Inventory Stress** spec'i de yazıldı
> (2026-05-24, bu commit) — `frontend/e2e-stress/specs/98-pos-kds-inventory.spec.js`.
> Task #8 (F8Z v2) sonrası baseline 73 → **74 spec** hedefi (F8Z.2 full-suite
> verification Task #29'da koşturuldu: targeted run 3✅/1✘/7-skip,
> serial-describe C'de durdu — predicted P0 KDS `/complete` cross-tenant
> mutate gerçekten yakalandı, mevcut "Make kitchen ticket 'complete' button
> respect hotel boundaries" hardening follow-up'ına bağlandı; backend fix
> sonrası full-suite re-baseline 74 spec). Spec doctrine: KDS catalog smoke
> (`/api/fnb/kitchen-display`) + kitchen_order lifecycle (pending→preparing
> →ready→served) + terminal-state guard (re-`complete` served ticket'ı
> ready'e revert ederse P1) + **P0 cross-tenant KDS IDOR** (pilot bearer
> status PUT / `/pos/kds/update-order-status` / `/complete` ile stress
> ticket mutate edemez — `kitchen.py:complete_kitchen_order` tenant-filter
> gap'i forensic context ile yakalanır, fix ayrı hardening task'ına devredilir)
> + idempotency replay (`POST /api/fnb/kitchen-order` `idempotency_key`
> honoring yok → distinct id = P1 finding) + inventory negative-stock
> guard (`POST /api/accounting/inventory/movement` `out` > available → 409,
> qty unchanged) + concurrent close race (5 paralel `out(1)` on qty=3
> → exactly 3 ok + final=0; final<0 → P0, ok>3 → P1) + **P0 cross-tenant
> inventory mutate** (pilot bearer stress item movement/adjustment → 4xx)
> + `stock-consumption` cross-tenant read (pilot body stress prefix
> içermez). Folio safety: KDS rows folio-bağımsız (`kitchen_orders`
> koleksiyonu), `post_to_folio=true` ASLA çağrılmaz; Xchange
> `POSTING_CHARGE` event'i tetiklenmez. WebSocket broadcast tenant-
> isolation indirect (list+mutate probes ile); direct spy mümkün değil
> → P2 REVIEW. Module-blocked doctrine: KDS bloklu → A–D skip; inventory
> bloklu → E/F/G/H/I skip; recipe yoksa → E/G skip + P2 (seed Task #11
> kapsamı dışı). `STRESS_COLLECTIONS` listesine `stock_consumption`,
> `inventory_movements`, `recipes`, `menu_items` eklendi (orphan-scrub
> safety net; spec-side `kitchen_orders` → cancelled primary path).
> Yeni helper: `assertPilotInventoryDeltaZero` (inline in spec) — pilot
> `inventory_items` `qty_delta=0` AND `count_delta=0` her batch sonunda
> doğrulanır. Detay: [`docs/drill_reports/20260524_stress_f8z2_kds_fnb_inventory.md`](./drill_reports/20260524_stress_f8z2_kds_fnb_inventory.md).
>
> **F8AF RMS Revenue Deep Stress** spec'i yazıldı (2026-05-24, bu commit) —
> `frontend/e2e-stress/specs/98-rms-revenue-deep.spec.js` (module
> `revenue_management`). Suite baseline 69 → **70 spec** (full-suite
> verification bir sonraki adım). Kapsam: Revenue Autopilot policy/queue/
> approve/reject lifecycle (mode FORCE `advisory`, original snapshot
> restore in cleanup) + Displacement analyze/compare/save + Demand
> Forecast POST + AI Pricing auto-publish dry-run + Hurdle CRUD/check.
> P0 cross-tenant IDOR: stress_token → pilot_hurdle PATCH/DELETE,
> stress_token → pilot_queue approve (≥400 hard-asserted, 2xx = P0
> + F8X-pattern fix direktif). Bogus-id probes her zaman koşar
> (`/queue/{00…0}/approve` + hurdle PATCH/DELETE). AI pricing batch
> sonunda dispatcher delta=0 ZORUNLU (kanal push tetiklenirse patlar).
> Forbidden surfaces: `/api/autopilot/run-cycle` + `/set-mode` (string
> concat sentinel'lar import edilir, literal asla spec source'unda geçmez).
> `STRESS_COLLECTIONS` += `revenue_autopilot_policies`,
> `revenue_approval_queue`, `revenue_apply_results`,
> `displacement_analyses`, `demand_forecasts`, `hurdle_rates`
> (orphan-scrub forward-compat anchors). F8AB spa doctrine (referans):
> catalog smoke + appointment lifecycle + atomic conflict guard
> (terapist/oda overlap → 409) + auto-pick + waitlist CRUD/promote +
> P0 cross-tenant IDOR + Idempotency-Key replay; spa folio safety
> (`charge_to_room=True + reservation_id=null` short-circuit) ve
> `STRESS_COLLECTIONS` += `spa_*` mevcut.
>
> **F8AD Konaklama Vergisi (TR accommodation tax) Dryrun** spec'i de
> yazıldı (2026-05-24, bu commit) — `frontend/e2e-stress/specs/98-konaklama-vergisi-dryrun.spec.js`,
> module `accommodation_tax`. Suite baseline 72 → **73 spec** (full-suite
> verification bir sonraki tur). Spec doctrine: module-block probe
> (`/api/finance/konaklama-vergisi/config` 403/404 → tüm bloklar SKIP +
> P2) + read-only smoke (config/report/declaration/declarations list/
> postings) + calculate validation (amount<=0 → 422, nights<1 → 422,
> aynı input → aynı net_tax idempotent) + write surface negative
> (PUT /config rate=999 → 422, finalize year=1999 → 422, bogus decl_id
> submit/pay/email/get/export → 4xx, bogus folio post-folio → 4xx,
> Idempotency-Key replay aynı bogus folio → replay 4xx) + **P0
> cross-tenant IDOR (hard-fail)** stress_token bearer + pilot harvest
> decl_id/folio_id → submit/pay/email/get/export/post-folio her biri
> için `expect(status).toBeGreaterThanOrEqual(400)`, 2xx = KESIN P0.
> Cron coupling guard: post-batch `external_calls` delta=0
> (`konaklama_vergisi_scheduler` Resend e-posta + `tga_scheduler` TGA
> outbound TETİKLENMEMELİ), `pilot_drift=0`. `STRESS_COLLECTIONS`
> listesine forward-compat `konaklama_vergisi_declarations`,
> `konaklama_vergisi_postings`, `tga_outbox` eklendi (gerçek backend
> koleksiyonları `tax_declarations` / `accommodation_tax_postings` /
> `integration_tga_outbox`; spec mutation YAPMAZ, orphan-scrub yalnız
> gelecekte stress_seed tagged seed eklenirse aktif olur). Detay rapor:
> [`docs/drill_reports/20260524_stress_f8ad_konaklama_vergisi.md`](./drill_reports/20260524_stress_f8ad_konaklama_vergisi.md).

> **HISTORICAL — bu blok 2026-05-24 tarihindeki resmi baseline'dı; güncel
> resmi pointer Run #167'dir (yukarıdaki "Latest verified baseline").** Bu
> green run o tarihte regression referansıydı. Detay raporlar:
> - F8R–F8W post-fix green: [`docs/drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md`](./drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md)
> - Önceki F8A..F8O baseline (referans): [`docs/drill_reports/20260523_stress_full_stress_suite_GREEN.md`](./drill_reports/20260523_stress_full_stress_suite_GREEN.md)

| Alan | Değer |
|---|---|
| Run tarihi | 2026-05-24 |
| Suite | Full Operational Stress Suite + **F8R–F8W Hardening Pack** (F8A+F8B+F8C+F8D+F8D-v3+F8E+F8F..F8O+**F8R+F8S+F8U+F8V+F8W**) |
| Workflow | GitHub Actions — Full Operational Stress Suite (CI one-shot) |
| Commit SHA (HEAD) | `ee7573b3` (HR docs filename sanitization — F8S P1 fix) |
| Contributing fixes (bu run) | `ee7573b3` (HR docs `_sanitize_doc_filename` upload+download), önceki: `a035568c` (starlette ≥1.0.1 PYSEC-2026-161), `8cee3050` (33B header read) |
| Spec count | **68** (`frontend/e2e-stress/specs/`, +5 F8R–F8W: 09/64/91/98/98B) |
| Başarısız test | **0** |
| FAIL adım | **0** |
| P0 / P1 | **0 / 0** |
| `external_calls` | `[]` (her modülde re-assert) |
| `pilot_drift` | **0** |
| Cleanup | idempotent (cleanup#1 deleted>0, cleanup#2 deleted=0) |
| F8R–F8W pack | ✅ 5 spec full-suite içinde geçti — auth_token_lifecycle · ws_tenant_isolation · export_artifact_idor · file_upload_security · ops_readiness |
| Final verdict | ✅ **GO** |

**Not:** Bir önceki run (HR docs sanitization öncesi) F8S `hr_docs_traversal_sanitize`
adımında 1 FAIL adım + 1 P1 vermişti (gerçek backend bug: raw `file.filename`
DB'ye literal yazılıyordu). `ee7573b3` ile fix uygulandı (`backend/domains/hr/router.py`
`_sanitize_doc_filename()` upload + download), republish → CI yeşil. Architect
verdict: **PASS** (sanitize stratejisi path traversal + Content-Disposition
header injection + URL-encoded/Unicode/nullbyte/CRLF tüm vektörleri kapsıyor).

**Önceki kademe raporları (20260517..20260523)** artık tarihsel referans
durumunda; canlı baseline olarak yukarıdaki tek run kullanılır.

## Mutlak kurallar (her faz için aynen geçerli)

- Pilot tenant'a **mutation yok** (yalnızca read; pilot_drift gate
  tüm spec'lerin son testidir).
- Gerçek **SMS / e-posta / OTA / payment / KVKK** çağrısı yok.
- `E2E_EXTERNAL_DRY_RUN=true` her zaman set.
- Cleanup idempotent (önce dry-run #1, sonra apply #2 no-op olmalı).
- `external_calls=[]` her batch sonunda re-assert.
- `failedTests=0`, `P0=0`, `P1=0`, final verdict ≥ **GO WITH WATCH**.
- Defans baseline: 5 gate (cleanup × 1, idempotent × 2, external_calls
  re-assert, pilot_drift), `module-blocked pattern` (endpoint 403/cache
  stale → `moduleBlocked=true` flag + P2 informational + A/B/C/D
  `test.skip()`, pilot_drift bağımsız çalışır).
- Seed: `STRESS_COLLECTIONS` listesi + `_build_<phase>_docs` factory +
  `stress_seed=True` + `stress_prefix=<prefix>` etiketleri, chunked
  insert + orphan cleanup loop.

## Faz listesi ve durumlar (kod-senkron — 2026-05-22 audit)

> **Senkronizasyon notu (2026-05-22):** Bu tablo `frontend/e2e-stress/specs/`
> dizinindeki **fiziksel dosyalara** göre yeniden senkronize edildi.
> Önceki turlarda F8F/G/H/K "Planlandı" + F8L "DONE/IN_PROGRESS" çelişkili
> görünüyordu; audit ile gerçek dosya envanteri eşleştirildi. Spec
> numaraları **eski rezerve aralıklar değil**, mevcut dosya adları.
> Toplam: **56 spec dosyası** (00–99 aralığında, 15 faz).

| Faz  | Kapsam                                                                  | Spec dosyaları (real)     | Status                                                       | ADR                                                       |
| ---- | ----------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------ | --------------------------------------------------------- |
| F8A  | Front Office / Folio / Housekeeping (day-turnover, room-move, mass, lifecycle, night-audit) | 00 / 01 / 02 / 03 / 04 / 05 / 06 / 08 | **DONE** — GO WITH WATCH (CI #38 / #55 PASS, tur-6..22) + v2 push 2026-05-18 | `docs/adr/2026-05-f8a-stress-evolution.md`                |
| F8B  | Guest Experience (QR / complaints / messaging / notifications)          | 10 / 11 / 12 / 13         | **DONE** — GO WITH WATCH (CI #55 PASS, tur-23..26)           | `docs/adr/2026-05-f8b-stress-evolution.md`                |
| F8C  | MICE / Event / Banquet / Group Operations                               | 14 / 15 / 16 / 17         | **DONE** — GO WITH WATCH (tur-5 CI YEŞİL, 2026-05-18)        | `docs/adr/2026-05-f8c-stress-evolution.md`                |
| F8D  | HR / İK / Staff / Shift / Leave / Department / Payroll v2 / Lifecycle v2 | 20 / 21 / 22 / 23 / 29 / 32 / 33 / 34 / 35 / 36 / 37 | **DONE v2** — Task #205 + #264 + İK v2 lifecycle (#268/#269/#270) merged (2026-05-19..22) — 11 spec, perf review + payroll dryrun (`/finalize` ASLA) + payroll lifecycle v2 + leave accrual + shift conflict + RBAC/PII/audit + IK lifecycle v2 (zimmet/uyarı/eğitim) | `docs/adr/2026-05-f8d-hr-staff-shift-evolution.md` (v2 section) |
| F8D-v3 | HR Coverage Extension (Profile detail / Self-service / Dept-Position masterdata / Offboarding / Shift coverage / Payroll export PII) | **38 / 38B / 39 / 39B / 35B / 33B** | **DONE** — 2026-05-22, 6 yeni spec — employee profile aggregate read + cross-tenant IDOR; staff self-service /payroll/me locked-only + cross-staff IDOR matrix; dept/position CRUD + FK guard + sync-from-staff idempotency; offboarding read-only + cross-tenant terminate guard + outstanding-equipment 409 (stress staff ASLA terminate edilmez P0 invariant); coverage-rules CRUD + min_staff validation; payroll export JSON/CSV/XLSX PII scan (TC/IBAN/JWT) + cross-tenant XLSX IDOR + anonymous reject. Mutlak kurallar: pilot mutation YOK, terminate force_release=false (irreversible YOK), external_calls=[]. CI verify bekleniyor. | TBD |
| F8E  | Finance / Cashier / Accounting / Invoice / City Ledger / Reports v2     | 24 / 25 / 26 / 27 / 28    | **DONE v2** — GO WITH WATCH (CI #42+, 2026-05-19)            | `docs/adr/2026-05-f8e-finance-stress-evolution.md`        |
| F8F  | Inventory / Stock / Purchasing / Supplier                               | **70 / 71**               | **DONE** — Task #197 merged (2026-05-19+) — inventory item CRUD + movement + negative-stock guard + low-stock + tenant isolation; supplier CRUD + PR→PO lifecycle + GRN/invoice matching + supplier-delete-when-used guard. **Warehouse transfer bilinçli scope dışı** (multi-target probe contract uygun değil) — F8F-v2 backlog. | TBD                                                       |
| F8G  | Sales / CRM / Offers / Contracts                                        | **80**                    | **DONE** — Task #198 merged — account/contact CRUD + duplicate tax-no guard + Lead→Opportunity (won/lost terminal) + contract lifecycle | TBD                                                       |
| F8H  | Reports / Analytics / Export                                            | **90**                    | **DONE** — Task #199 merged — dashboard KPI (pms/accounting/revenue) + operational reports (occupancy/revenue/aging/HR/finance/inventory) + CSV/XLSX/PDF export + PII/token mask + pagination + cache invalidation | TBD                                                       |
| F8I  | Admin / RBAC / Settings / Audit                                         | 30 / 31                   | **DONE** — Task #193 merged (2026-05-19) — 13 test, role matrix + cross-tenant settings drift + audit/PII guard | TBD                                                       |
| F8J  | Full 24h Hotel Simulation — tüm modüller birlikte                       | 99 (chained scenario)     | **DONE** — Task #201 merged (2026-05-19)                     | TBD                                                       |
| F8K  | Guest-facing public flows (online check-in / NPS / digital key / KVKK)  | **60 / 61 / 62**          | **DONE** — Task #196 merged — public online check-in (anonymous/garbage/tampered JWT + ID metadata + KVKK) + NPS/reviews + KVKK consent + digital-key anonymous/cross-tenant + KVKK lifecycle. **QR token rotation deep → F8Q § 63.** | TBD                                                       |
| F8L  | Channel Manager + Webhooks (Exely / HotelRunner / Outbox / SXI bus)     | 50 / 51 / 52 / **52B**    | **DONE** — Task #195 merged (2026-05-19) — 22 test (architect-iter-4): Exely IP+payload+tenant-injection+replay + HotelRunner HMAC sig contract+surface coverage+logs scope + Outbox status/events/RBAC + Conflict Queue cross-tenant scope. **v2 (Task #6, 2026-05-24)** — yeni spec `52B-cm-stop-sale-bulk-resolve.spec.js` (+9 test): Stop-sale CB (`GET /unified-rate-manager/circuit-breakers`) tenant-prefix strip + leak guard + anon deny; Bulk-resolve (`POST /conflict-queue/bulk-resolve`) partial-failure isolation + dedup last-room-wins + max 50 (422) + anon/RBAC + **P0 cross-tenant IDOR** (stress→pilot booking_id) + real-succeeded informational + Z-step pilot_drift/external_calls. Pending-seed gap (P2 REVIEW): stress seed pipeline pending_assignment üretmez (OTA import external_calls invariant'ı engelliyor) → error-path coverage deterministic, real-succeeded coverage informational. | TBD                                                       |
| F8M  | GraphQL + B2B API (resolver isolation / API key scope)                  | 40 / 41                   | **DONE** — Task #194 merged (2026-05-19) — 11 test, GraphQL introspection + resolver isolation + cross-tenant injection + B2B api-key lifecycle/scope/revocation | TBD                                                       |
| F8M v2 | B2B Sub-Router Tenant Isolation Matrix (11 X-API-Key sub-routers) | **41B** | **DONE** — Spec yazıldı 2026-05-24, full-suite verification 2026-05-26 Run #143 (commit `3b3891d`, 84 spec, failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0, verdict GO WITH WATCH). 11 alt-router matrix invariantları (A collection GET pilot_tid leak guard + assertNoTokenLeak + assertPiiMasked, B P0 cross-tenant IDOR 4xx, C P0 missing/bogus X-API-Key 401/403, D per-subrouter scope P2 REVIEW, E pilot_drift + external_calls) GREEN baseline'a girdi. Gerçek P0/P1 bulgu YOK. Tek REVIEW: stress tenant agency seed eksik (`agencies_list_len=0` → A/B/C/D module-blocked SKIP, E invariant testi PASS — doktrin gereği SKIP ≠ PASS, IDOR/auth-bypass coverage tam doğrulanamadı). Follow-up: B2B agency pilot seed task'ı (deeper isolation coverage). | `docs/drill_reports/20260524_stress_f8m_v2_b2b_matrix.md` + `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` |
| F8N  | Reservation lifecycle deep (create/modify/cancel/no-show/group)         | 95 (deep batch)           | **DONE** — Task #200 merged (2026-05-19)                     | TBD                                                       |
| F8O  | AI / Automation Dry-run (upsell-insights / dynamic-pricing / no-show risk) | 42 / 43 / 44           | **DONE** — Task #206 merged (2026-05-19+) — 20 test (3 spec); vendor LLM HTTP çağrısı YOK (briefing.ai_powered=false guard) + autopilot run-cycle/set-mode + ML train kapalı kapı (source-scan) + cross-tenant insight/pricing/no-show leak guard. Dosya 44 disk'te → IN_PROGRESS değil DONE. | `docs/adr/2026-05-f8o-ai-automation-dryrun.md` |
| F8P  | Cross-tenant pen-test (guests / folios / charges / messages / hr_staff dedicated probes) | 96 | **DONE** — 2026-05-21 — 5 step, 5 yüzey: per-surface withModuleProbe + scanLeaks (tenant_id_exact + PILOT_/PROD_ marker) + pilot sample ID harvest → IDOR (200+pilot_tid=P0, 200+no evidence=P1) + assertPiiMasked + final invariants. A/B/C all-blocked → SKIP doctrine (false PASS önleme). | TBD |
| F8Q  | **Security & External Surface Hardening** — MICE BEO + push batch dry-run + QR token tamper/cross-tenant + per-endpoint RL boundary | **18 / 45 / 63 / 97** | **DONE** — 2026-05-22 commit `3f49b966` — 4 spec: MICE BEO/kitchen-ticket/ops-sheet/payment-schedule read-only + cross-tenant + F&B send P2 REVIEW (endpoint yok) · Push batch (DISABLE_EXPO_PUSH=1) 100-notif enqueue + delivery-logs/activity feed PII + cross-tenant + invalid-payload graceful · QR tampered/cross-tenant/bulk staff PII + ROOM_QR_SECRET rotation surface P2 REVIEW (endpoint yok) · Burst N=60 per surface (public/auth/GraphQL/B2B/reports) + tenant isolation (pilot sample post-burst healthy). CI verify bekleniyor; lokal smoke disk'te. | TBD |

### F8F–F8N expansion contract (Task #192 Foundation — **LEGACY PLANNING**)

> **2026-05-22 sync notu:** Aşağıdaki tablo Task #192 foundation
> turunda yazıldığı orijinal planlama sözleşmesidir; spec numaraları
> ve test sayıları **plan aşamasındaki rezerve değerlerdir**, gerçek
> implementasyondan sapmıştır. Asıl durum yukarıdaki "Faz listesi ve
> durumlar" tablosundadır (kod-senkron). Bu blok geriye dönük
> referans için korunmuştur; çelişki durumunda üst tablo bağlayıcıdır.

Her yeni faz için aşağıdaki sözleşme zorunludur (F8A–F8E baseline'ı bozmadan ek olarak):

| Faz  | Spec dosyaları                          | Test sayısı | Risk     | Dry-run kuralı                                                                                                              | Cleanup kapsamı                                                                       | Pilot drift | external_calls |
| ---- | --------------------------------------- | ----------- | -------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------- | -------------- |
| F8F  | 30-inventory · 31-stock · 32-purchasing · 33-supplier | 4–6 | MEDIUM   | Procurement PO `approve` lokal; supplier portal push YOK (`E2E_EXTERNAL_DRY_RUN=true`)                                      | `inventory_items`, `stock_movements`, `suppliers`, `purchase_orders` (stress_prefix)  | =0          | []             |
| F8G  | 34-crm-leads · 35-offers · 36-contracts | 3–5         | MEDIUM   | CRM offer email send dry-run (Resend silent); contract e-signature provider call YOK                                        | `crm_leads`, `offers`, `contracts` (stress_prefix)                                    | =0          | []             |
| F8H  | 40-reports-finance · 41-reports-ops · 42-export | 3–5 | LOW      | Report run read-only; export PDF/XLSX in-memory, dosya yazımı yok                                                           | Yok (read-only); cache invalidation idempotent                                        | =0          | []             |
| F8I  | 30-admin-rbac · 31-settings-audit       | 13 (Task #193 DONE) | **HIGH** | RBAC negative test (403 expect); audit log read; per-role user create + login + idempotent delete; tenant info PATCH restore-on-cleanup | `users` (stress_prefix per-role test users), `audit_logs` ASLA silinmez (KVKK retention) | =0          | []             |
| F8J  | 50-24h-full                             | 1 (chained) | HIGH     | Tüm F8 path'lerinin chained dry-run koşusu; tek spec, çok step                                                              | Önceki fazların cleanup helper'larını çağırır (composite)                             | =0          | []             |
| F8K  | 60-online-checkin · 61-nps-reviews · 62-qr-token-expiry · 63-public-ratelimit | 5–7 | **CRITICAL** | KVKK consent, ID metadata-only (binary upload YOK), digital-key issue/revoke dry-run, public RL 429 boundary | `online_checkin_submissions`, `guest_reviews`, `nps_responses`, `digital_keys`        | =0          | []             |
| F8L  | 50-cm-webhooks-exely · 51-cm-hotelrunner-outbox · 52-cm-outbox-idempotency | 20 (Task #195 IN_PROGRESS) | **CRITICAL** | Exely IP-gate + payload-size limit + empty/garbage payload reject + tenant injection + replay burst; HotelRunner HMAC sig contract (6 probe) + 3 webhook surface coverage + logs/events cross-tenant + sig-mode classification; Outbox status delta no-op + /events PII/token + RBAC bypass + Conflict Queue stres scope + anonymous deny | `outbox_events` (read-only stress_tid scope), `webhook_raw_payloads` (touch yok), `bookings` (conflict_queue read-only) | =0          | []             |
| F8M  | 40-graphql-tenant-isolation · 41-b2b-api-key-scope | 11 (Task #194 DONE) | **CRITICAL** | GraphQL introspection policy + bookings/rooms/dashboard/nested resolver isolation + cross-tenant injection probes (var spoof / pagination cursor); B2B api-key create→info→revoke→post-revoke deny + missing/garbage/valid scope + cross-tenant api-keys GET disclosure | `agency_api_keys` (stress agency, idempotent DELETE in afterAll) | =0          | []             |
| F8N  | 72-reservation-batch · 73-cancel-noshow · 74-group-multiroom · 75-overbooking-waitlist | 6–8 | HIGH | F8A lifecycle deep dive; CM outbox event consistency F8L ile overlap            | `bookings`, `group_bookings`, `folios` (stress_prefix)                                | =0          | []             |

**GO/NO-GO eşiği (tüm fazlar)**: `failedTests=0`, `P0=0`, `P1=0`, `cleanup#2 idempotent`, `pilot_drift=0`, verdict ≥ `GO WITH WATCH`.

**module-blocked pattern fallback**: Her spec'te endpoint 403 / 404 / RBAC fail → `moduleBlocked=true` flag + P2 informational + A/B/C/D `test.skip()`, pilot_drift bağımsız çalışır (F8C/D/E doctrine, `withModuleProbe` helper).

**Foundation helpers (Task #192 ekledi)** — `frontend/e2e-stress/fixtures/stress-helpers.js`. Tüm helper'lar `testInfo` + `module` ilk argümanları alır (rec/finding annotation emit etmek için), mevcut `recPerf` / `assertNoExternalCallsPostBatch` ile aynı konvansiyon:
- `assertPilotDriftZero(testInfo, module, request, pilotToken, baseline)` — pilot bookings count read-only diff, drift>0 → P0 finding emit.
- `assertNoExternalCallsPostBatch(testInfo, module, batchName, stressState, request, pilotToken)` — tur-28 per-batch delta doctrine (mevcut, korunuyor).
- `assertPiiMasked(testInfo, module, responseBody, fields=[...])` — telefon/email/TC/passport/IBAN gibi PII alanları masked olduğunu doğrular; plain match bulursa P0 finding emit (KVKK / F8I / F8K / F8M kritik).
- `withModuleProbe(request, token, endpoint, opts={})` — endpoint 403/404/network → `{moduleBlocked: true, status, body, reason}` döner; spec'ler A/B/C/D step'lerini güvenle skip eder, pilot_drift bağımsız çalışır.

**Reporter aggregation (Task #192 notu)** — `markdown-reporter.mjs` modül tablosu zaten **dinamik** çalışıyor (rec annotation'lardaki `module` field'ı serbest string, otomatik aggregate). Yeni faz etiketleri (admin_rbac, settings_audit, graphql_isolation, b2b_api, cm_exely, cm_hotelrunner, cm_outbox, public_checkin, public_nps, public_kvkk, inventory_stock, purchasing_supplier, crm_offers, reports_export, reservation_deep, full_24h) ek mapping gerekmeden tabloda görünür. Task kapsamında yalnız "Broken Buttons / Wrong Business Rule" triage regex'i F8F–F8N terminolojisine genişletildi (RBAC/KVKK/PII/outbox/webhook/graphql/b2b/report/dashboard/export → businessRule bucket; UI keyword'leri buttonFindings'de izole).

---

## Coverage Gaps / Added Phases

Bu bölüm, mevcut F8A-F8D fazlarında **tamamlanmış olmasına rağmen kapsam
dışı kalmış yüzeyleri** ve **roadmap'e eklenen yeni fazları** kayıt altına
alır. Her madde takip eden tur ya da yeni faz'a backlog olarak girer.

### F8A backlog — Front Office + Folio + Housekeeping (v2 turu)

Mevcut: day-turnover (checkout/walk-in), room-move (positive/negative/race),
folio mass (charge/payment/split/audit), housekeeping (transitions/OOO).

**Eksik (backlog):**
- ✅ **Reservation create / modify / cancel batch** — `specs/05-reservation-lifecycle.spec.js` A/B/C (2026-05-18).
- ✅ **No-show conversion** — `specs/05-reservation-lifecycle.spec.js` D (pre-create confirmed bookings → no-show, 2026-05-18).
- ✅ **Overbooking guard** — `specs/05-reservation-lifecycle.spec.js` E (positive overbooking-check + duplicate POST reject, P0 finding emit if double-booking created, 2026-05-18).
- ✅ **Open-folio refund / void flow** — `specs/04-folio-mass.spec.js` C3/C4/C5 (refund + void-charge + void-payment with RBAC short-circuit handling, 2026-05-18).
- ✅ **Group bookings / multi-room reservation** — `specs/05-reservation-lifecycle.spec.js` F/G (group-reservations POST + multi-room POST with 3 rooms, 2026-05-18).
- **CM outbox event consistency** — booking değişikliklerinin SXI bus
  event'lerine yansıması (CM-Hardening serisi var; stress'te yok). **→ F8L'e devredildi.**
- ✅ **Explicit night audit batch** — `specs/06-night-audit.spec.js` (business-date GET + run + re-run idempotency + exceptions list, 2026-05-18).

### F8B backlog — Guest Experience (v2 turu)

Mevcut: room QR (public submit / staff transitions / token guard), service
requests (filter/bulk PATCH), complaints (resolve/compensation), messaging
dry-run (email/sms/whatsapp).

**Eksik (backlog):**
- **Guest reviews / NPS submit + aggregation** — F8B kapsamında yok.
- **Online check-in public flow** — public guest surface, yüksek riskli;
  form submit + state machine test edilmedi.
- **KVKK consent** — online check-in akışının parçası, ayrı stress yok.
- **ID upload dry-run / metadata-only** — gerçek dosya yüklemesi YOK,
  sadece metadata + size limit + MIME guard.
- **Digital key issue/revoke dry-run** — mobile app digital key flow.
- **Push notification batch dry-run** — `DISABLE_EXPO_PUSH=true` gate
  altında smoke.
- **QR token expiry / rotation** — invalid token testi var; expired
  token + secret rotation testi yok.

### F8C backlog — MICE / Sales / Banquet (v2 turu)

Mevcut: events (lead→tentative→definite + payment schedule), opportunities
(stage transitions), leads (funnel), competitor (rates).

**Eksik (backlog):**
- **Event-day banquet execution** — BEO print/export, F&B order send,
  day-of resource booking — execution layer yok.
- **BEO print/export dry-run** — PDF/document gen yüzeyi.
- **F&B order send dry-run** — restoran/mutfak entegrasyon yüzeyi.
- **Cross-event resource conflict** — aynı space + aynı saat 2 event
  → conflict reject.
- **Same space + same time reject** — yukarının deterministik testi.
- **MICE package apply flow** — 3 package seed var, apply path yok.
- **Opportunity won/lost terminal state** — won/lost explicit test
  edilmedi (ADR'da "yok" not'u var).

### F8D backlog — HR / İK / Staff / Shift / Leave (v2 turu — genişletildi)

Mevcut (v1): staff org (list/bulk create), attendance (clock-in/out),
leave (request/decision), shift swap (consent/decision lifecycle).

**Eksik (backlog — F8D'nin v2 turunda tam kapanış için):**
- **Performance review lifecycle** — initiate → manager feedback →
  employee acknowledge. (3 perf_review seed var; lifecycle yok.)
- **Payroll smoke** — calculate dry-run → finalize blocked/dry-run →
  export preview. **`/finalize` ASLA tetiklenmeyecek**, sadece preview
  + dry-run hesap path.
- **Department hierarchy / org chart traversal** — flat list var; parent-
  child traversal, ancestry, role mapping derinliği yok.
- **Shift conflict reject** — aynı staff + overlapping shift create → 409.
- **Shift coverage** — department minimum coverage check (örn. her
  vardiyada ≥ 2 housekeeping personeli).
- **Leave balance accrual / carry-over smoke** — balance probe var;
  monthly accrual + year-end carry-over hesap path yok.
- **HR audit log** — staff create/update + leave decision audit trail.
  KVKK PII change-log için kritik.
- **RBAC** — staff user başka departmanın restricted record'larına
  erişemez (cross-department leak negative test).
- **PII guard** — phone / identity / payroll fields response'larda
  masked; log/report exportlarında ham PII olmamalı.

### Genel (cross-cutting) backlog
- ✅ **Rate-limit boundary** — F8Q § 97 (per-endpoint burst N=60, tenant isolation post-burst).
- ✅ **Tenant isolation cross-check** — F8P § 96 (guests/folios/charges/messages/hr_staff dedicated probes).
- ✅ **GraphQL surface** — F8M § 40.
- ✅ **B2B API** — F8M § 41.
- ✅ **Webhook endpoints** (Exely / HotelRunner IP allowlist) — F8L § 50/51.
- ✅ **AI integration paths** (upsell / dynamic pricing / no-show risk) — F8O § 42/43/44.

---

## Hardening Backlog (F8R+ — 2026-05-22 audit önerileri)

Bu bölüm, kullanıcı audit'i (2026-05-22) sonrası tespit edilen ve F8A–F8Q
kapsamı dışında kalmış **gerçek production saldırı yüzeylerini** kayıt
altına alır. Her madde ileride yeni bir faz veya v2 push için backlog.

### F8R — Export Artifact IDOR — ✅ DONE (2026-05-23)
- **Spec:** `frontend/e2e-stress/specs/91-export-artifact-idor.spec.js`
- **Module:** `export_artifact_idor`
- **Kapsam:** 9 export surface (hr_payroll_run · hr_shifts · hr_attendance ·
  hr_leave · hr_overtime · hr_payroll_csv · admin_leads_csv ·
  pms_commission · b2b_analytics). Path-ID surface'lerde pilot ID harvest
  → stress_token download → 403/404 zorunlu; 2xx + body pilot marker →
  P0 IDOR. Self-tenant smoke (content-type expected class, 5xx → P1).
  Unauth probe (no bearer) → 2xx + content → P0. Binary-aware
  `downloadProbe` (Content-Type/Length header + 2KB body sniff).
- **Doctrine:** module-blocked her surface için tekil (list probe non-2xx
  → o surface SKIP, diğerleri çalışır). Final invariant (drift=0,
  external_calls=[]) bağımsız her zaman çalışır.

### F8S — File/Document Upload Security — ✅ DONE (2026-05-23)
- **Spec:** `frontend/e2e-stress/specs/64-file-upload-security.spec.js`
- **Module:** `file_upload_security`
- **Kapsam:** HR docs (`POST /api/hr/staff/{id}/documents`, 5 MB cap,
  MIME allow-list) + housekeeping photo (`POST /api/housekeeping/upload-photo`,
  Pillow magic-bytes). Probe matrix: oversized → 413 · exe/svg MIME → 400/415 ·
  HTML-as-PDF polyglot (HR, P2 informational header-trust gotcha) ·
  HTML-as-PNG/PDF-as-JPEG polyglot (HK, P0 if accepted) · empty file → 400 ·
  path-traversal filename → sanitize zorunlu · cross-tenant download
  (stress doc → pilot token = 403/404, pilot doc → stress token = 403/404) ·
  unauth POST → 4xx zorunlu.
- **Doctrine:** her surface ayrı module-block (staff probe vs rooms probe);
  diğer surface çalışmaya devam. Final invariant bağımsız.

### F8U — Auth Token Lifecycle — ✅ DONE (2026-05-23)
- **Spec:** `frontend/e2e-stress/specs/98-auth-token-lifecycle.spec.js`
- **Module:** `auth_token_lifecycle`
- **Kapsam:** fresh login (paylaşılan stress bearer ASLA logout edilmez —
  ayrı session) · token shape (access_token + refresh_token + expires_in) ·
  refresh rotation (access + refresh diff zorunlu, refresh body single-use)
  · old refresh after rotation → 4xx (P0 if reused) · logout invalidates
  hem access hem refresh (Redis pub/sub auth invalidation gotcha guardı) ·
  garbage/random/fake-shape/tampered (real JWT signature byte-flip) reject
  · cross-scope guard (refresh token Bearer olarak `/auth/me` → 4xx, P0
  if accepted) · final invariants.
- **Doctrine:** serial mode (logout chain); module-blocked yok (creds env
  yoksa A-G SKIP, H bağımsız).

### F8V — WebSocket / Live Panel Isolation — ✅ DONE (2026-05-23)
- **Spec:** `frontend/e2e-stress/specs/98B-websocket-tenant-isolation.spec.js`
- **Module:** `ws_tenant_isolation`
- **Kapsam:** `/api/enterprise/ws/live?token=...` (enterprise_live L86) ·
  unauth/garbage/random token → close(4001) veya data frame yok (data frame
  = P0) · valid stress_token connect → frame'lerde pilot_tid literal yok
  (leak = P0) · cross-tenant subscribe spoof (4 farklı payload shape) →
  pilot_tid frame'de görünmemeli · final invariants. Dynamic `ws` import
  (Node 20 no native WebSocket; frontend/node_modules/ws bundled).
- **Doctrine:** `ws` import veya endpoint 404 → A/B/C SKIP, D bağımsız.

### F8W — Ops Readiness Smoke — ✅ DONE (2026-05-23)
- **Spec:** `frontend/e2e-stress/specs/09-ops-readiness-smoke.spec.js`
- **Module:** `ops_readiness`
- **Kapsam:** `/health` + `/health/ready` + `/api/health` 2xx zorunlu ·
  backup last age (5 endpoint candidate prob) — >36h REVIEW, >7d P1 ·
  CM outbox depth (>10k = P1) + conflict queue (>100 open = P1) ·
  liveness probes (ws/stats · observability/health · system-health/live ·
  admin/cache/warmer-status) 5xx = P1 · final invariants.
- **Doctrine:** read-only nightly cron sinyal yakalayıcı. Tek probe
  unreachable → P2 informational, suite SKIP değil.

### F8T — Staff Self-Service Scope (önerilen)
- **Spec:** `38-hr-staff-self-service.spec.js` (planlandı, henüz yok)
- **Kapsam:** personel kendi vardiyası/maaş/izin/performans kayıtlarını
  görür · başka personelin kayıtlarını göremez (object-level RBAC) · kendi
  izin talebini açabilir · kendi PII'sini sınırlı update edebilir (telefon
  evet, TC/IBAN hayır).
- **Neden:** F8D HR modülü çok büyüdü; staff role token'ları için
  object-level isolation ayrı doğrulanmalı (`/hr/payroll/me` Task #264'te
  fail-closed allow-list ile var, diğer self-service endpoint'ler için
  paralel test yok).

### F8U — Auth Token Lifecycle (önerilen)
- **Spec:** `98-auth-token-lifecycle.spec.js` (planlandı, henüz yok)
- **Kapsam:** refresh token rotation · revoked refresh token reject ·
  logout invalidates access+refresh · device-bound token (mobile) · expired
  access token reject · concurrent refresh race.
- **Neden:** F8I admin RBAC + F8M B2B API key test ediyor; standart user
  JWT lifecycle (mobil app dahil) ayrı pen-test gerektirir
  (`JWT_EXPIRATION_MINUTES`/`REFRESH_TOKEN_EXPIRATION_DAYS` env'leri
  contract olarak doğrulanmalı).

### F8V — WebSocket / Live Panel Isolation (önerilen)
- **Spec:** `98-websocket-tenant-isolation.spec.js` (planlandı, henüz yok)
- **Kapsam:** stress token WS subscribe · pilot event görünmez ·
  unauthorized subscribe reject · room/channel spoof reject · message
  injection cross-tenant.
- **Neden:** Canlı panel/notification/dashboard stream HTTP test'lerle
  yakalanmaz; Redis pub/sub auth invalidation gotcha mevcut ama
  multi-tenant WS isolation ayrı stress yok.

### F8W — Ops Readiness Smoke (önerilen)
- **Spec:** `98-ops-readiness-smoke.spec.js` (planlandı, henüz yok)
- **Kapsam:** readiness endpoint PASS/REVIEW · backup status not stale
  (`docs/REPLIT_OPS_CHEATSHEET.md` Atlas-managed backup metrik) · rollback
  metadata endpoint · CM backlog status (outbox depth + conflict queue
  count) · cache warm-up smoke.
- **Neden:** Production Safety Pack 8/8 DONE ama stres suite içinde mini
  readiness smoke yok; nightly cron stres run'ı bu sinyali yakalamalı.

### F8X — E-fatura / E-arşiv dry-run — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98-efatura-earsiv-dryrun.spec.js`
- **Module:** `efatura_earsiv_dryrun`
- **Kapsam:** `/api/invoices` list/stats read-only probe · invoice create
  invalid VKN (4 örnek: short/long/non-numeric/all-zero) + invalid TCKN
  (4 örnek: invalid-checksum/all-same/all-zero/non-numeric) validation
  4xx zorunlu · cross-tenant invoice PUT IDOR (stress_token + pilot
  invoice ID → 403/404 zorunlu, 2xx = P0) · ERP sync surface (`logo-integration/sync`,
  `netsis-integration/sync`) module-probe + post-batch external-calls
  delta=0 (gerçek GİB/Logo/Netsis HTTP yasak).
- **Doctrine:** module-blocked per-surface (her endpoint için 403/404 →
  P2 informational). Real GİB dispatch riski olmadığı assertNoExternalCallsPostBatch
  ile her batch sonu doğrulanır.

### F8Y — KBS / Jandarma identity reporting dry-run — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/65-identity-reporting-kbs-jandarma-dryrun.spec.js`
- **Module:** `identity_reporting_dryrun`
- **Kapsam:** `/api/kbs/guests` · `/api/kbs/queue` · `/api/kbs/reports` ·
  `/api/kbs/setup-info` read-only probe · invalid TC samples (5 örnek)
  validation 4xx zorunlu · missing-identity payload → 4xx veya
  `status=quarantined` PASS · KBS_TEST_MODE prefix guard (TEST- prefix'siz
  reference reddedilmeli) · cross-tenant queue claim IDOR (stress_token +
  pilot job ID → 403/404 zorunlu) · post-batch external-calls delta=0
  (gerçek Emniyet/Jandarma HTTP yasak).
- **Doctrine:** module-blocked per-surface. KBS_TEST_MODE OFF iken prefix
  guard probe REVIEW olur (informational).

### F8Z — Payment / POS reconciliation dry-run — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98-payment-pos-reconciliation-dryrun.spec.js`
- **Module:** `payment_pos_reconciliation`
- **Kapsam:** `/api/cashier/current-shift`, `/api/cashier/period-report`,
  `/api/pos/orders`, `/api/pos/tables` read-only probe · folio payment
  bogus folio ID → 404 zorunlu · negative amount → 4xx zorunlu (P1 if
  accepted) · cross-tenant folio payment IDOR (stress_token + pilot
  folio ID → 403/404 zorunlu, 2xx = P0 — gerçek para mutation) ·
  manual-transaction Idempotency-Key replay → same id veya 409 zorunlu
  (double-post P1 if distinct ids) · post-batch external-calls delta=0
  (gerçek Iyzico/Stripe/POS HTTP yasak).
- **Doctrine:** NO write probe outside cashier own shift; idempotency
  probe shift YOK ise SKIP+P2 (fake PASS yok). Cross-tenant payment
  attempt P0 hard-fail (`expect().toBeGreaterThanOrEqual(400)`).

### F8AA — KVKK retention / deletion / anonymization — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/66-kvkk-retention-deletion-anonymization.spec.js`
- **Module:** `kvkk_retention`
- **Kapsam:** `/api/gdpr/data-requests` · `/api/checkin/online/id-photos` ·
  `/api/checkin/online/settings/id-photo-retention` read-only probe ·
  bogus photo ID delete → 404 zorunlu · cross-tenant ID-photo delete
  IDOR (stress_token + pilot photo ID → 403/404 zorunlu, 2xx = P0 KVKK
  breach) · bulk-delete cross-tenant → `deleted_count=0` zorunlu (>0 = P0) ·
  GDPR data-requests yanıtında pilot tenant_id literal yok (varsa P0) ·
  anonymize/guest-hard-delete endpoint backend'te explicit YOK → P2
  informational (roadmap backlog: F8AA v2 endpoint kontratı gerekir).
- **Doctrine:** WRITE probe minimum (yalnız bogus-id 404 + cross-tenant
  rejection). Real misafir profilini anonymize/silmiyoruz.

### F8AB — Spa & Wellness Operational Stress — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98-spa-wellness-operational.spec.js`
- **Module:** `spa_operations`
- **Kapsam:** `/api/spa/services|therapists|rooms|availability|daily-summary|waitlist`
  read-only probe · appointment lifecycle (scheduled→in_progress→completed
  + no_show + cancelled) · atomic conflict guard (aynı therapist+room+slot
  → 409, 2xx = P1) · auto-pick (therapist_id+room_id omit → backend
  deterministik atama; assigned tuple zorunlu) · waitlist CRUD/patch/delete
  + manual promote · invalid status guard (`invented_status` → 4xx) ·
  Idempotency-Key replay (aynı tuple+key → same id veya 409, distinct
  ids = P1) · P0 cross-tenant IDOR (pilot bearer stress-created
  appointment status change / delete / waitlist patch / delete → 4xx
  zorunlu, 2xx = P0) · cleanup idempotent (DELETE round-trip, ikinci
  pass 404 zorunlu) · post-batch external_calls delta=0 + pilot_drift=0
  her test'te.
- **Folio safety:** `charge_to_room=True + reservation_id=null` short-circuit
  (`_post_to_folio` ve `bus.publish(POSTING_CHARGE)` ASLA tetiklenmez);
  external_calls invariant batch sonunda doğrulanır. `completed` transition
  `require_finance` istiyor — stress admin super_admin → PASS, 403 olursa
  P2 informational (role gap, lifecycle invariant intact).
- **Doctrine:** module-blocked pattern (services/therapists/rooms probe
  herhangi biri 403/404 → A/B/C/D/E `test.skip` + P2 informational, Z
  cleanup + final invariants bağımsız). `STRESS_COLLECTIONS` listesine
  `spa_appointments`, `spa_waitlist`, `spa_services`, `spa_therapists`,
  `spa_rooms`, `spa_locks` eklendi (orphan-scrub safety net; spec-side
  DELETE primary cleanup path'tir).
- **Baseline:** 68 → **69 spec** (full-suite verification bir sonraki tur).

### F8AC — Golf Operational Stress — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98-golf-operational.spec.js`
- **Module:** `golf_operations`
- **Kapsam:** `/api/golf/courses|players|tee-sheet|daily-summary|bookings`
  read-only probe (courses auto-seed default, super_admin POST fallback) ·
  booking lifecycle (confirmed→checked_in→completed + no_show + cancelled)
  · atomic conflict guard: **(a)** slot capacity overflow (party_size +
  booked > capacity → 409, 2xx = P1) · **(b)** same player_ids OR guest_id
  at same tee_time → 409, 2xx = P1 · folio-post endpoint contract
  (`/bookings/{id}/folio-post`): reservation_id=null → 400 zorunlu,
  bogus id → 404, replay → 409 idempotent · invalid status guard
  (`invented_status` → 4xx) · Idempotency-Key replay with same player_id
  (distinct ids = P1) · **P0 cross-tenant IDOR** (pilot bearer
  stress-created booking status change / delete / folio-post → 4xx
  zorunlu, 2xx = P0) · cleanup idempotent (DELETE round-trip, ikinci
  pass 404 zorunlu) · post-batch external_calls delta=0 + pilot_drift=0
  her test'te.
- **Folio safety:** `charge_to_room=True + reservation_id=null` short-circuit
  (`_post_to_folio` ve `bus.publish(POSTING_CHARGE)` ASLA tetiklenmez,
  router.py L558-559); external_calls invariant batch sonunda doğrulanır.
  `completed` ve `/folio-post` `require_finance` istiyor — stress admin
  super_admin → PASS, 403 olursa P2 informational (role gap, lifecycle
  invariant intact).
- **Doctrine:** F8AB spa pattern'inin birebir kardeşi. module-blocked
  pattern (courses/players probe herhangi biri 403/404 → A/B/C/D/E
  `test.skip` + P2 informational, Z cleanup + final invariants bağımsız).
  `STRESS_COLLECTIONS` listesine `golf_courses`, `golf_players`,
  `golf_tee_bookings`, `golf_locks` eklendi (orphan-scrub safety net;
  spec-side DELETE bookings primary path, players + self-seeded courses
  unified cleanup loop ile).
- **Baseline:** 69 → **73 spec** (F8X/F8Y/F8Z/F8AA/F8AB + F8AC dahil;
  full-suite verification bir sonraki tur).

### F8Z v2 — POS Deep Lifecycle Stress — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98-pos-deep-lifecycle.spec.js`
- **Module:** `pos_deep_lifecycle`
- **Kapsam:** POS v2 lifecycle (`POST /api/pos/v2/orders` → `/close` →
  `/void`, `post_to_folio=false` + `booking_id=null` safe path) · split-check
  (`POST /api/pos/check-split` equal/by_item/custom, sum ≤ total invariant)
  · table-transfer negative contract (`POST /api/pos/transfer-table` bogus
  from_table → 404 zorunlu) · validate-room-charge bogus + cross-tenant
  probe (PII leak guard) · idempotency-key replay on create + close
  (service-level `idempotency_key` body field → same order id or 4xx) ·
  terminal-state guard (void closed order → idempotent flag, close-after-
  void → 4xx, re-void → idempotent veya 4xx) · **P0 cross-tenant IDOR**
  (pilot bearer stress-created order'a close/void/transfer → 4xx zorunlu,
  2xx = P0; check-split tenant-agnostic computational, body'de stress
  identifier görülürse P0) · cleanup idempotent (void round-trip, ikinci
  pass idempotent veya 4xx terminal-state zorunlu) · post-batch
  external_calls delta=0 + pilot_drift=0 her test'te.
- **Folio safety:** `close_order(post_to_folio=False, booking_id=null)`
  asla `folio_charges` insert etmez ve Xchange `POSTING_CHARGE` event'i
  publish etmez (service-side short-circuit). external_calls invariant
  batch sonunda doğrulanır.
- **Doctrine:** F8AB spa + F8AC golf pattern'inin POS kardeşi. Module-
  blocked pattern (`GET /api/pos/orders` probe 403/404 → A/B/C/D/E/F/G/H/I
  `test.skip` + P2 informational, Z cleanup + final invariants bağımsız).
  `STRESS_COLLECTIONS` listesine `pos_orders`, `pos_transactions`,
  `table_layouts`, `kitchen_orders`, `pos_outlets`, `pos_menu_items`,
  `happy_hour_rules`, `pos_room_charge_restrictions` eklendi (orphan-scrub
  safety net; spec-side void primary path). Backend kodu değişmedi; v1
  spec (`98-payment-pos-reconciliation-dryrun.spec.js`) dokunulmadı.
- **Baseline:** 72 → **73 spec** (full-suite verification bir sonraki tur).
### F8AG — 2FA TOTP Lifecycle Stress — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98C-twofa-totp-lifecycle.spec.js`
- **Module:** `twofa_lifecycle`
- **Kapsam:** `/api/2fa/status|setup|setup/confirm|disable|regenerate-backup-codes|policy`
  + `/api/auth/login` (challenge gate) + `/api/auth/2fa/verify`. Lifecycle:
  status probe → setup (pending secret + otpauth URI + QR data URL) →
  confirm wrong code (400/401) → confirm correct (enabled=true + ≥8 backup
  codes) → login challenge (`requires_2fa=true` + `challenge_token`,
  `access_token=""`) → verify happy-path (exchange challenge for access)
  → **challenge_token single-use replay** (aynı challenge ikinci verify →
  4xx, 2xx = P0; `consumed_jtis` unique index regression sinyali) →
  brute-force boundary (17 invalid burst → ≥1× 429; threshold 15/60s
  endpoint-scoped, bleed yok) → backup code single-use via verify path
  (REVIEW eğer backend backup'ı /verify'da kabul etmiyorsa; kabul ediyorsa
  ikinci use 4xx zorunlu, 2xx = P0) → regenerate wrong code (4xx) →
  regenerate correct (≥8 yeni code) → **same-window TOTP replay** (aynı
  code anında ikinci /regenerate → 4xx zorunlu, 2xx = P0 = Bug CB
  `consumed_totp` unique index regression) → policy GET → **P0 cross-tenant
  IDOR matrix** (pilot bearer ile /status read + setup/disable/regenerate
  mutate dener → pilot kendi state'ini görür, stress user state'i
  ASLA değişmez; `enabled_before == enabled_after && backup_remaining_before
  == backup_remaining_after` invariant, ihlal = P0; ek olarak
  `pilotDisable.status ≥ 400` + `pilotRegen.status ≥ 400` hard-fail
  `expect().toBeGreaterThanOrEqual(400)`) → disable cleanup (primary path
  test H'de) + afterAll backup-code fallback (CRITICAL: 2FA enabled bırakılırsa
  diğer tüm spec'lerin paylaşılan bearer login refresh'i challenge döner,
  full-suite çöker).
- **TOTP üretimi:** Self-contained node:crypto HMAC-SHA1 + base32 decode
  helper (`totpAt`/`currentTotp`); pyotp/otplib bağımlılığı yok. Setup
  response `secret` field plaintext (manual fallback) — bu spec onu
  client-side TOTP üretimi için kullanır.
- **Doctrine:** module-blocked (status probe 403/404/0 → A-G skip + P2;
  2FA already enabled probe time → P1 + hard fail çünkü secret elde değil,
  manuel operator cleanup gerekir). Shared stress_token bearer setup/confirm/
  disable/regen yüzeylerine kullanılır (current_user-scoped, F8U fresh-login
  doctrine'ine UYGUN çünkü logout/refresh dokunulmuyor). Fresh login sadece
  verify happy-path + replay + throttle + backup tests için (her test
  kendi challenge'ını alır). Final invariants H'de: pilot_drift=0 +
  external_calls=[]. `STRESS_COLLECTIONS` listesine `consumed_totp` eklendi
  (replay-guard koleksiyonu; TTL 180s ile Mongo auto-clean, ancak orphan-scrub
  forward-compat safety net). Backend writes `stress_seed`/`stress_prefix`
  tag konvansiyonunu uygulamıyor — entry observability-only.
- **Baseline:** 73 → **74 spec** (F8AG dahil; full-suite verification bir
  sonraki tur — Workflows kapalı, e2e CI sandbox'ta runnable değil).

### F8AH — Ops Surface Smoke Stress — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98-ops-surface-smoke.spec.js`
- **Modüller:** `cross_property_rollup` · `shift_handover` · `webhook_admin_dlq` · `eod_report` · `booking_holds` (5 module-block tek spec).
- **Kapsam (her blok):** module-blocked probe (403/404 → A/B/C/D/E `test.skip` + P2 informational, Z cleanup + final invariants bağımsız) · smoke (happy-path read + minimal-safe write) · **P0 cross-tenant IDOR** (pilot bearer ile stress kaynağı mutate/read = 2xx → P0 hard-fail) · negative validation (P1) · cleanup idempotent (DELETE round-trip, ikinci pass 404/no-op zorunlu) · post-batch `external_calls=[]` + `pilot_drift=0` her test'te try/finally.
- **Module detayları:**
  - **A) cross_property_rollup** — `GET /api/cross-property/guests/search` chain rollup yüzeyi (get_system_db bypass). Stress→pilot leak (returned tenant_id == pilot_tid) = P0. Pilot→stress leak (pilot returns stress tenant_id rows) = P0 (super_admin chain bypass policy review — operator decides).
  - **B) shift_handover** — `POST/GET/PATCH ack/DELETE /api/pms/shift-handover` full lifecycle + open-count + invalid `shift` 4xx + **P0 IDOR**: pilot bearer cross-tenant ack/delete (find_one_and_update + delete_one tenant_id filter doğrulaması).
  - **C) webhook_admin_dlq** — `/api/webhooks/status|deliveries|dlq` router-wide `require_super_admin_guard`. **Stress bearer 2xx = P0** (non-super-admin bypass). Pilot super_admin 2xx = expected smoke; `tenant_id` query filter narrow değil widen ediyorsa P1. DLQ retry/dismiss write yüzeyi out-of-scope (read-only smoke).
  - **D) eod_report** — `/preview` + `/pdf` (yesterday business_date); `_collect(current_user.tenant_id, ...)` yapısal tenant filtre → leak imkânsız ama defensive (response body.tenant_id == stress_tid → P0). **`/send` ASLA çağrılmaz** (mail external_calls invariant'ı kırar — discipline + runtime guarantee).
  - **E) booking_holds** — synthetic `booking_id=STRESS_F8AH_*` + `room_id=STRESS_F8AH_*` (service opaque tag, FK yok); create → status → IDOR (pilot status/confirm/delete) → stress re-check (has_hold still true zorunlu, false = P0) → self-DELETE → sweep role-guard probe (200 veya 403, 5xx = P1).
- **STRESS_COLLECTIONS:** `shift_handovers` eklendi (orphan-scrub safety net; spec-side DELETE primary). `room_night_locks` zaten F8A altında (booking_holds residue). cross_property/webhook_admin/eod read-only → ek koleksiyon yok.
- **Baseline:** 73 → **74 spec** (F8AH eklendi; full-suite verification bir sonraki tur).

### F8AF — RMS Revenue Deep Stress — ✅ DONE (2026-05-24, spec written)
- **Spec:** `frontend/e2e-stress/specs/98-rms-revenue-deep.spec.js`
- **Module:** `revenue_management`
- **Kapsam:** Revenue Autopilot (`/api/revenue-autopilot/policy|queue|process|
  queue/{id}/approve|reject`) lifecycle — mode FORCE `advisory` (full_auto =
  arka plan gerçek apply riski; closed door); process→queued→approve+reject
  · Displacement (`/api/displacement/analyze|compare|save|history|market-
  overview`) · Demand Forecast GET/POST · AI Pricing auto-publish dry-run
  (`/api/rms/ai-pricing/auto-publish-rates`) · Hurdle CRUD
  (`POST /api/hurdle-rates/`, `PATCH /{id}`, `DELETE /{id}`, `GET /check`
  allowed+blocked) · cross-tenant IDOR + bogus-id probes.
- **P0 hard-asserts:** stress_token → pilot_hurdle PATCH/DELETE ≥400 ·
  stress_token → pilot_queue approve ≥400 (silent 200+success:false = F8X
  regression risk → fix direktif: `backend/modules/revenue_autopilot/
  service.py` `approve_item`/`reject_item`/`rollback_item` `if not item:
  raise HTTPException(404,…)`) · advisory mode → action=auto_applied = P0
  (mode enforcement broken) · bogus-id `00…0` UUID approve/PATCH/DELETE
  ≥400 (pilot harvest'a bağımsız always-on).
- **Safety:** AI pricing auto-publish batch sonunda dispatcher delta=0
  ZORUNLU (channel push tetiklenirse `assertNoExternalCallsPostBatch`
  patlar). Forbidden literal source-scan: `FORBIDDEN_AI_AUTOPILOT_RUN`
  (`/api/autopilot/run-cycle`) + `FORBIDDEN_AI_AUTOPILOT_SETMODE`
  (`/api/autopilot/set-mode`) — F8O doctrine.
- **Doctrine:** Module-blocked pattern (dashboard/policy/queue probe
  herhangi biri 403/404 → A..G `test.skip` + P2 informational, Z cleanup
  + final invariants bağımsız). Setup'ta original policy snapshot al,
  Z3'te best-effort restore. Pilot harvest empty olduğunda IDOR yolu
  P2 SKIP (vector not exercised — fake PASS yok).
- **Stress collections:** `revenue_autopilot_policies`,
  `revenue_approval_queue`, `revenue_apply_results`,
  `displacement_analyses`, `demand_forecasts`, `hurdle_rates` orphan-scrub
  forward-compat anchor (mevcut router'lar `stress_seed` tag pass-through
  yapmadığı için no-op).
- **Baseline:** 69 → **70 spec** (full-suite verification bir sonraki tur).

### F8AE — VCC + PCI Compliance Stress — ✅ DONE (2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/98-vcc-pci-compliance.spec.js`
- **Module:** `vcc_pci_compliance`
- **Kapsam:** `/api/pms/reservations/{id}/vcc[/status|/reveal]` + DELETE
  + `/api/compliance/pci/{status,controls,report.csv,attestation}`
  read smoke · VCC lifecycle (store → status → reveal #1) · audit
  invariant via `/api/reservations/{id}/full-detail.history`
  (vcc_stored + vcc_revealed + vcc_deleted) · 3-view reveal limit
  hard guard (4th reveal **MUST 403**, 2xx = P0 PCI Req 3.2 breach) ·
  PAN regex sweep `\b(?:\d[ -]?){13,19}\b` (masked değerler hariç) +
  forbidden-key sweep (`*_enc` ciphertext leak guard) · CSV
  formula-injection guard (`safe_writerow` line-prefix `=/+/-/@`) ·
  **P0 cross-tenant IDOR bidirectional** (pilot bearer → stress VCC
  status/reveal/delete/store ALL 4xx; stress bearer → pilot booking
  VCC status/reveal ALL 4xx; 2xx = P0 catastrophic disclosure) ·
  cleanup idempotent (DELETE round-trip, ikinci pass 404 zorunlu) ·
  post-batch external_calls delta=0 + pilot_drift=0 her test'te.
- **Test PAN:** Luhn-valid sentinel `4111…1111` konkatenasyon ile
  yazılır (string split source-scan false-positive guard). AES-256-GCM
  ile yalnız stress tenant'a şifrelenir; hiçbir PSP'ye iletilmez.
- **Doctrine:** F8X–F8AA compliance pattern'inin VCC/PCI kardeşi.
  module-blocked fallback (VCC veya PCI probe 403/404 → A/B/C/D
  `test.skip` + P2 informational, Z cleanup + final invariants
  bağımsız). 409 store conflict (prior partial run residue) → P2 +
  cleanup'a id ekleyip skip (fake-PASS yok). `STRESS_COLLECTIONS`
  listesine `vcc_cards` + `reservation_activity_log` eklendi
  (orphan-scrub safety net; spec-side DELETE primary path'tir).
- **Baseline:** 73 → **74 spec** (full-suite verification bir sonraki tur).

### F8O v2 — AI prompt PII redaction (önerilen)
- **Kapsam:** AI prompt PII redaction snapshot · AI recommendation audit
  trail · human approval required guard · AI response explainability alanı
  zorunlu · AI output deterministic schema validation.

### F8K v2 — QR token rotation deep (önerilen — F8Q § 63 başlangıç)
- ✅ Tamper / cross-tenant / staff PII bulk — F8Q § 63 (DONE).
- **Eksik:** secret rotate old token grace behavior · revoked token TTL
  · raw token/secret log leak guard · audit log emit.

### F8F v2 — Warehouse Transfer (DONE — Task #9, 2026-05-24)
- **Spec:** `frontend/e2e-stress/specs/72-warehouse-transfer-procurement.spec.js`
  (module `inventory_transfer_procurement`).
- **Kapsam:** 5 segment — A) warehouse transfer probe
  (`POST /api/accounting/inventory/movement?movement_type=transfer` →
  422/400 fail-closed; 2xx = P0); B) partial GRN lifecycle
  (sent→partially_received→received + rejected-qc no-stock guard +
  overage 4xx); C) PO cancellation guard (empty reason 422 / cancel+GRN
  409 / closed→cancelled 409); D) supplier `credit_limit` probe (Pydantic
  extra-ignore → P2 product gap) + delete-when-used guard 409 + P0
  cross-tenant IDOR (pilot bearer PUT/DELETE supplier + POST status +
  POST GRN → 4xx mandatory); E) final invariants + idempotent cleanup
  second-pass 404 assertion.
- **STRESS_COLLECTIONS:** `proc_suppliers|proc_purchase_requests|
  proc_purchase_orders|proc_goods_receipts|proc_counters` orphan-scrub
  safety net (spec teardown primary).
- **Doctrine:** module-blocked (suppliers GET probe non-2xx → A/B/C/D
  skip + P2; E always runs) · pilot_drift=0 + external_calls=[] per
  test in try/finally · inventory_item_id=null PO lines (no
  housekeeping_inventory side-effect) · idempotent cleanup
  (PO cancel → supplier delete; 404/409 absorb).
- **Baseline:** 73 → **74 spec** (full-suite verification next round).
- **Neden:** F8F § 70/71 bilinçli olarak transfer'i scope dışı bıraktı;
  F8F v2 transfer contract'ını fail-closed olarak doğrular + partial
  receipt + cancel guard + credit_limit gap'ini belgeler.

---

## Yeni fazlar (detay specs)

Yeni faz şablonları aşağıda. Her faz için 4-5 spec, F8A-D'deki defans
baseline (cleanup × 1, idempotent × 2, external_calls re-assert,
pilot_drift) **zorunlu** ve `module-blocked pattern` fallback olarak hep
açık.

### F8K — Guest-facing public flows

**Spec'ler:**
- **60 — Online check-in submit**: 30 booking için public check-in form
  POST (PII validation, state machine: pending → submitted → verified).
- **60 — KVKK consent**: explicit consent flag set/unset audit trail,
  consent withdrawal flow.
- **60 — ID metadata dry-run**: ID upload sadece metadata
  (filename / size / MIME / hash); gerçek binary upload YOK; AES-256-GCM
  encryption stub.
- **61 — Review/NPS submit + aggregation**: 50 public review POST
  (rate-limited), aggregation endpoint (average / breakdown).
- **62 — QR token expiry/rotation**: expired token → 403, rotated
  `ROOM_QR_SECRET` ile eski token reject.
- **62 — Digital key issue/revoke dry-run**: mobile app key issue
  request → token gen (real BLE broadcast YOK), revoke → invalidation.
- **63 — Public rate-limit boundary**: explicit 429 boundary test per
  public endpoint (online check-in / review / QR submit).
- **Pilot drift = 0** + **external_calls = []** (her spec son testleri).

**Risk notu:** Public surface = en geniş saldırı yüzeyi; KVKK + PII
guard'ları F8K'nın özünde.

### F8L — Channel Manager + Webhooks

**Spec'ler:**
- **64 — Exely webhook IP allowlist**: positive (whitelisted IP →
  accepted) + negative (non-whitelisted → 403). `EXELY_IP_WHITELIST`
  literal list (CIDR DEĞİL, gotcha).
- **64 — HotelRunner webhook payload validation**: signature verification,
  invalid signature → 401, malformed payload → 422.
- **65 — Booking created/modified/cancelled/no-show event outbox**:
  her event tipinin outbox'a yazıldığını + payload schema'nın doğru
  olduğunu doğrula.
- **65 — SXI bus event distribution**: event publish → subscriber'lar
  invoke edildi (DRY_RUN mode: gerçek HTTP YOK, sadece dispatcher attempt
  log'u).
- **66 — OTA sync dry-run**: full inventory push + rate push, gerçek
  Exely/HotelRunner endpoint'ine isabet YOK (CM circuit breaker per-
  connection açık).
- **66 — Duplicate webhook idempotency**: aynı event_id × 2 → tek kez
  apply edildi (unique compound index).
- **67 — Invalid signature reject**: bypass attempt (forged HMAC) → 401.
- **Pilot drift = 0** + **external_calls = []** (unless explicitly
  mocked under DRY_RUN with `mock_dispatcher=True`).

**Risk notu:** SXI bus + outbox = production hardening serisi
(CM-Hardening) test surface'inin tamamı; gotcha doc `verify_exely_whitelist.py`
referansı.

### F8M — GraphQL + B2B API

**Spec'ler:**
- **68 — GraphQL tenant isolation**: cross-tenant query attempt → boş
  result veya 403; resolver-level `tenant_id` filter zorunluluğu.
- **68 — GraphQL resolver RBAC**: privileged resolver (örn. finance
  reports) non-admin token ile → 403.
- **68 — N+1 / pagination safety**: deep nested query → query depth
  limit + cost analysis; cursor pagination boundaries.
- **69 — B2B API key scope**: API key sadece kendi scope'undaki
  endpoint'lere erişebilir.
- **69 — Invalid API key reject**: malformed / revoked key → 401.
- **70 — Cross-tenant API key reject**: tenant A'nın key'i tenant B'nin
  resource'una erişemez.
- **70 — Rate-limit boundary**: B2B API per-key rate-limit explicit 429
  boundary.
- **71 — Audit log**: B2B API her call audit trail'e yazıldı.
- **Pilot drift = 0** + **external_calls = []**.

**Risk notu:** Threat-model'de "Highest-risk areas" listesinde
`backend/graphql_api/` ve `backend/routers/b2b_api/` var → F8M kritik.

### F8N — Reservation lifecycle deep

**Spec'ler:**
- **72 — Batch reservation create**: 100 reservation POST, çeşitli
  oda tipleri / tarih aralıkları.
- **72 — Modify dates**: 50 reservation tarih güncelleme, inventory
  lock release + re-acquire atomicity.
- **72 — Modify room type**: 30 reservation room type upgrade/downgrade,
  rate recalculation.
- **73 — Cancel**: 50 reservation cancel, folio close + lock release.
- **73 — No-show conversion**: 30 reservation `mark_no_show` → cancelled
  veya checkout-virtual, terminal-state guard.
- **74 — Group booking**: 5 group × 10 oda, group_id ortak, master
  folio + sub-folios.
- **74 — Multi-room reservation**: 1 misafir N oda (block booking).
- **75 — Overbooking reject**: occupancy > capacity attempt → 409.
- **75 — Waitlist / pending assignment**: full occupancy iken yeni
  request → waitlist; opening varsa auto-assign.
- **75 — CM outbox event consistency**: her lifecycle event'i outbox'a
  yansıdı (F8L ile overlap'lı; integration smoke).
- **Pilot drift = 0** + **external_calls = []**.

**Risk notu:** F8A walk-in/checkout test ediyor ama reservation
**lifecycle**'ın bütünü test edilmiyor → F8N en yüksek operational risk
kapatma fazı.

---

## Öncelik önerisi (sıralı)

1. **F8E Finance** — devam eden, tur-5 CI #41 bekleniyor, bitirilmeli.
2. **F8N Reservation lifecycle deep** — operasyonel risk en yüksek, F8A
   üzerine deep dive.
3. **F8L Channel Manager + Webhooks** — production hardening surface'i,
   outbox + IP allowlist + idempotency.
4. **F8D-HR extension (v2)** — payroll/perf-review/PII guard tamamlanması,
   KVKK compliance.
5. **F8K Guest-facing public flows** — KVKK + public surface güvenliği.
6. **F8I Admin/RBAC** — threat-model EoP kategorisi kapatması.
7. **F8J Full 24h Simulation** — tüm fazlar yeşilden sonra final
   integration drill.

(F8F Inventory / F8G Sales-CRM / F8H Reports / F8M GraphQL-B2B sırası
yukarıdaki yedi ana hat tamamlandıktan sonra planlanır.)

---

## F8D — sonraki başlatma için pre-flight notları (legacy v1, korunuyor) + v2 scope (AÇIK)

Bu bölüm F8D v1 done olmasına rağmen **v2 turu için kullanıcı tarafından
açık tutulan** scope listesini içerir. Her madde F8D v2 spec'lerine
girer (planlanan spec dosyaları: `frontend/e2e-stress/specs/29-32`).
F8D v2 başlatılana kadar bu liste değiştirilmez.

### Kapsam (kullanıcı 2026-05-19 direktifi, kesin)

1. **Personel (Staff)** — `/api/hr/staff*`, `/api/hr/employees*`. Bulk
   create + role assignment + activation/deactivation + termination
   lifecycle. PII fields (TC kimlik, telefon) masked response.
2. **Departman** — `/api/hr/departments*`. Hierarchy create
   (parent_id), org chart traversal (ancestry), role mapping, code
   prefix isolation. Department delete cascade smoke.
3. **Vardiya (Shift)** — `/api/hr/shifts*`. Schedule generation
   (weekly/monthly), swap request lifecycle (request → approve/reject),
   conflict reject (aynı staff + overlapping window → 409), department
   minimum coverage check.
4. **İzin (Leave)** — `/api/hr/leaves*`. Request → approve/reject →
   balance decrement, monthly accrual smoke, year-end carry-over,
   pending vs active queue separation.
5. **Görev (Task)** — `/api/operations/tasks*` veya `/api/hr/tasks*`.
   Assignment + status transition (pending → in_progress → completed),
   escalation (overdue → manager notify, in-app only), bulk-close.
6. **Housekeeping-Personel ilişkisi** — Department coverage minimum
   check (örn. her vardiyada ≥ 2 housekeeping personeli), room
   assignment by staff role, housekeeping task → staff_id binding,
   on-duty filter doğru staff'ı çekiyor.
7. **Yetki izolasyonu (RBAC)** — Cross-department record access reject
   (staff A başka department'ın staff/leave/shift kayıtlarını
   okuyamaz/değiştiremez). Manager scope = sadece kendi department'ı.
   Negative test: HR-only endpoint'lere ops staff token ile erişim →
   403.
8. **Audit** — Staff create/update/terminate, leave decision (approve/
   reject), shift swap decision tüm aksiyonlar `audit_logs` koleksiyonuna
   actor_id + before/after snapshot ile yazılıyor. KVKK PII change-log
   için kritik (örn. telefon güncelleme → eski/yeni masked log).
9. **Cleanup** — HR koleksiyonları (`staff_members`,
   `hr_departments`, `hr_positions`, `attendance_records`,
   `leave_requests`, `leave_balances`, `shift_schedules`,
   `shift_swap_requests`, `performance_reviews`, `payroll_records`)
   prefix-scoped scrub idempotent. Orphan scrub run × 2 = no-op
   (delta=0 ikinci runda).

### Dış servis riski

- **KVKK ID-photo**: Quick-ID integration var (`/api/quickid/*`), ama
  HR staff create flow bu yola dokunmuyor (guest-only). `module-blocked
  pattern` her durumda fallback.
- **Payroll**: `/finalize` ASLA tetiklenmeyecek, sadece dry-run hesap
  path + export preview. `E2E_EXTERNAL_DRY_RUN=true` global gate
  zorunlu (payroll provider entegrasyonu varsa engellenir).
- **Notifications**: In-app only (`db.notifications`), Resend/SMS
  provider call yok (F8B cleanup zaten kapsar).

### Backend route taraması (F8D v2 session'ında yapılacak)

- `backend/routers/hr/*` veya `backend/domains/hr/router/*` — staff /
  department / position / leave / shift / attendance / performance
  endpoint envanteri.
- `backend/routers/operations/*` veya `backend/domains/operations/*` —
  task endpoint envanteri.
- `audit_logs` koleksiyonuna yazan trigger noktaları (`core/audit.py`
  helper) — hangi HR aksiyonların audit'lendiği listesi.
- `backend/core/rbac.py` — manager scope (department-bound)
  enforcement detayları.

## Yapılış sırası (her faz için)

1. **Backend route taraması** (rg ile ilgili namespace).
2. **Seed extension** (`backend/domains/admin/router/stress.py`):
   `STRESS_COLLECTIONS` += yeni koleksiyonlar, `_build_<phase>_docs`
   factory.
3. **4-5 spec** (frontend/e2e-stress/specs/): Setup → A/B/C/D → external
   re-assert → pilot drift; serial mode, 1500ms gap,
   `callTimedWithBackoff` (429 retry).
   - **Task #34 pacing contract (zorunlu, 2026-05-27)**: Tüm yeni spec'ler
     `callTimed` / `callTimedWithBackoff` üzerinden istek atmalı — bu iki
     primitive Task #34'te per-token client-side pacer (write=100/min,
     default=250/min, anonymous=50/min, prod ceilingleri 120/300/60 altında
     emniyet payı) + otomatik 429 retry (retry-after-aware, 3 deneme, 65s
     cap) ile sertleştirildi. Doğrudan `request.post(...)` / `request.get(...)`
     çağrısı YASAK (pacer'ı atlatır, 485+ test suite'inde bucket'ı patlatır).
     Rate-limit boundary spec'leri (`97-rate-limit-boundary`,
     `41B-b2b-subrouter-matrix` burst) kasıtlı 429 üretmek için
     `{ noPacer: true, noBackoff: true }` opt-out ile çağırmalı; bu
     kombinasyon RL davranışını ölçen testler haricinde KULLANILMAZ.
   - Pacer module-scoped (`workers:1 + fullyParallel:false` doctrine'i
     sayesinde tek event loop) ve bearer token'ın son 12 karakteri ile
     key'lenir. Stress + pilot bearer'ları ayrı bucket'larda izole edilir
     → cross-tenant izolasyon test'leri pacer pencereleri bağlamında da
     korunur. Detay: `frontend/e2e-stress/fixtures/stress-helpers.js`
     Task #34 yorum bloğu (line ~112) + drill report
     `docs/drill_reports/20260524_stress_full_stress_suite_f8ah_NOT_GREEN.md`.
4. **Drill report** (`docs/drill_reports/<date>_stress_<phase>_*.md`).
5. **ADR** (`docs/adr/<yyyy-mm>-<phase>-*.md`).
6. **replit.md** "Gotchas" → tek-satırlık pointer.

## Acceptance contract (her faz)

- failedTests=0, P0=0, P1=0
- external_calls_made=[]
- pilot_drift=0
- cleanup idempotent (#2 no-op)
- final verdict ≥ GO WITH WATCH

Bu dosya stress test serisi için tek doğruluk kaynağıdır. Faz
tamamlandıkça status sütunu güncellenir; backlog maddesi yeni v2 turunda
veya yeni faz'a taşınır.

## CI / GitHub Actions

**Dosya:** `.github/workflows/stress.yml` — adı: **Full Stress Suite
(one-shot)** (Task #192 review fix; eski "F8A Stress Suite" adı kapsam
F8A→F8E genişlediği için terk edildi).

**Ne koşturur:** `cd frontend && yarn test:e2e:stress` — `-g` filter YOK,
chunking YOK. Tüm spec'ler tek Playwright process'inde, `workers=1`,
sıralı:

- F8A specs 00..06, 08 — Front Office + Folio + Housekeeping
- F8B specs 10..13 — Guest Experience (QR/complaints/messaging)
- F8C specs 14..17 — MICE / Event / Banquet / Sales
- F8D specs 20..23 — HR / Staff / Shift / Leave
- F8E specs 24..28 — Finance / Cashier / Accounting / Reports / Currency
- F8F–F8N specs 30..75 — Inventory/Purchasing/Reports/RBAC/Public/CM/GraphQL/Reservation-deep/24h (Task #192-#201 sırasıyla eklendi)

**Trigger:**
- Nightly cron `30 2 * * *` (UTC).
- Manuel `workflow_dispatch` (opsiyonel `report_tag` + `room_count`
  input'larıyla).

**Hedef tenant:** `STRESS_TENANT_ID` (pilot DEĞİL). Pre-flight gate
`STRESS_TENANT_ID == PILOT_TENANT_ID` ise fail-closed.

**Concurrency:** `group: stress-suite-one-shot`,
`cancel-in-progress: false` — aynı stress tenant'ta paralel seed/cleanup
çakışmasını engeller; ikinci run sıraya girer, koşan run iptal edilmez
(orphan data önleme).

**Faz bazlı ayrı workflow yok** — full suite tek bir koşuda kapsamı
veriyor. İleride F8F/G/H/I/J eklendiğinde de aynı dosya kullanılır
(timeout 60dk tampon var). Faz-bazlı koşu lokal Replit sandbox'ta
`-g <pattern>` ile yapılır (110s tool-budget gotcha — `docs/GOTCHAS.md`
"F8A Stress Suite").

**Hard-fail gates:** Playwright exit code, globalTeardown invariants
(cleanup × 2 idempotent + pilot_drift), drill report `Final verdict`
satırının `NO-GO` olmaması.

**Outputs (artifact):**
- `playwright-stress-report` — Playwright HTML report (30 gün).
- `stress-drill-report` — `docs/drill_reports/*_stress_<TAG>.md` (90
  gün); path tek kaynaktan (`STRESS_REPORT_TAG` job env).
- `stress-test-results` — trace + video + screenshot (14 gün).

**Slack:** `STRESS_SLACK_WEBHOOK_URL` secret set ise failure / NO-GO ve
GO WITH WATCH bildirimleri gönderilir; webhook job-level env'de
(`SLACK_WEBHOOK_URL`) bağlı olduğundan `if: failure() &&
env.SLACK_WEBHOOK_URL != ''` condition güvenli çalışır.
