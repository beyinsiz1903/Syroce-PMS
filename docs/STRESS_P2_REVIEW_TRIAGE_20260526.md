# Stress P2 / REVIEW Triage — 2026-05-26 (Run #143)

> **Baseline:** Full Stress Suite (one-shot) · Run **#143** · commit `3b3891d` ·
> 84 spec · **556 test** · adımlar **1087 PASS / 0 FAIL / 46 REVIEW / 73 SKIP** ·
> bulgular **P0=0 · P1=0 · P2=60 · P3=1** · `external_calls=[]` ·
> `pilot_drift=0` (30 → 30) · cleanup idempotent (#1=7734 → #2=0) ·
> verdict **GO WITH WATCH**.
>
> **Kaynak:** reporter artifact (CI Run #143). Drill report
> `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md`.
> Bu doküman, baseline'ı GO'a taşıyacak P2/REVIEW backlog'unu yapılandırır.
>
> **Doktrin kuralı (değişmez):** P2/REVIEW kalemleri **PASS'e
> downgrade edilmez**. GO WITH WATCH overclaim edilip "GO" denmez.
> Kritik güvenlik sinyali `P0=P1=0`'dır ve korunmuştur.

---

## 1) Executive summary

84 spec / 556 test'lik Full Stress Suite Run #143'te:

- **0 başarısız test**, **0 başarısız adım** — paket end-to-end yeşil koştu.
- **0 P0**, **0 P1** — kritik veya yüksek-öncelikli güvenlik/iş kuralı
  bulgusu yok. Cross-tenant mutate, IDOR, auth bypass, kasa, retention,
  POS KDS, RMS, 2FA throttle gibi para/güvenlik yüzeylerinde regression
  yok.
- **60 P2** + **1 P3** informational bulgu — verdict'i bloklamayan
  ama backlog'a alınması gereken kalemler. Tamamı dört kategoriden birine
  düşüyor: (i) module-blocked SKIP (RBAC by-design veya endpoint not
  deployed), (ii) fixture / seed eksik, (iii) data-state veya örneklem
  sebepli inconclusive, (iv) observability / contract gap.
- **46 REVIEW** adım — bulgu seviyesi değil, adım seviyesi (insan onayı
  bekleyen "evidence kabul edilebilir mi?" satırları). PASS'e dönüştürülmedi.
- **Pilot tenant mutation = 0**, **gerçek dış servis çağrısı = 0**,
  **cleanup idempotent** — pilot trust narrative invariantları PASS.
- **Verdict GO WITH WATCH** F8 doktrini altında kabul edilen yeşil
  sonuçtur (`verdict ≥ GO WITH WATCH`).

Bu rapor, GO WITH WATCH → GO'a giden yolun **takip backlog'u**dur. P2/REVIEW
kalemleri sınıflandırılır, pilot-blocking / non-blocking olarak ayrılır,
bir sonraki hardening sprint'i için sıralı plan çıkarılır.

---

## 2) What GO WITH WATCH means

F8 stres-suite doktrinimizde verdict üç kademedir:

| Verdict | Şartlar | Kabul? |
|---|---|---|
| **NO-GO** | herhangi `P0 > 0` ya da `failedTests > 0` ya da `external_calls ≠ []` ya da `pilot_drift > 0` ya da cleanup idempotent değil | ❌ — release blocker |
| **GO WITH WATCH** | `P0 = P1 = 0` + tüm invariant gate'ler PASS + ama `P2 > 0` veya `REVIEW > 0` | ✅ kabul — backlog ile sürdür |
| **GO** | yukarıdakilerin tümü + `P2 = 0` ve `REVIEW = 0` | ✅ kabul — saf yeşil |

Run #143 invariantları:

- `failedTests == 0` ✅
- `failedSteps (FAIL) == 0` ✅
- `P0 == 0` ✅ (kritik bulgu yok)
- `P1 == 0` ✅ (yüksek-öncelikli bulgu yok)
- `external_calls_made == []` ✅ (hiçbir gerçek SMS/e-posta/OTA/ödeme çağrısı yok)
- `pilot_drift == 0` ✅ (pilot bookings 30 → 30, sızıntı yok)
- Cleanup idempotent ✅ (#1=7734 silindi → #2=0)
- Architect review PASS ✅

Bu nedenle baseline **kabul edilir yeşil**dir. "GO" iddia edilmesi
doktrinen yanlış olur çünkü P2=60 ve REVIEW=46 hâlâ açıktır. Pilot ve
yatırımcı iletişiminde "GO WITH WATCH" net olarak iletilir.

---

## 3) P2 / REVIEW category taxonomy

60 P2 + 46 REVIEW kalemi dört şemsiye kategoriye düşer. Kategori,
ileride alınacak aksiyonun türünü belirler.

| Kategori | Tanım | Tipik root cause | Aksiyon türü |
|---|---|---|---|
| **A — Module-blocked SKIP (RBAC by design)** | Stres admin rolünün **kasıtlı olarak** erişemediği RBAC alanları (MICE, CRM, HR per-role) | 403 rbac_denied, by-design | Spec'i alternatif role ile çalıştır veya açıkça "doctrine: out of scope" kabul et |
| **B — Endpoint not deployed / observability gap** | API yolu 404 veya observability contract'ı stres env'de yoktu | endpoint absent, shape değişti, secret unset | Backend route mount, observability endpoint ekle, secret provision |
| **C — Fixture / seed gap** | Stres tenant'ında gerekli seed (agency, recipe, folio, payment) yok | seed factory eksik | Seed factory'e ekle, idempotent + cleanup-safe |
| **D — Data-state / sample-sebepli inconclusive** | Önceki batch örneklemi tüketmiş veya state out-of-scope kalmış | execution-order coupling | Spec'i bağımsız set-up ile reorder veya isolated fixture |

Dağılım (provisional — artifact backfill required for exact counts):

| Kategori | P2 (yaklaşık) | REVIEW (yaklaşık) | Toplam |
|---:|---:|---:|---:|
| A — RBAC by design | ~28 | ~22 | ~50 |
| B — Endpoint / observability gap | ~16 | ~12 | ~28 |
| C — Fixture / seed gap | ~10 | ~8 | ~18 |
| D — Data-state | ~6 | ~4 | ~10 |
| **Toplam (artifact ground truth)** | **60** | **46** | **106** |

> **Backfill required:** Toplam P2=60 / REVIEW=46 artifact'ten kesin
> doğrulanmıştır. Ancak kategori başına dağılım reporter `reason=`
> alanlarının her bulgu için tek-tek sınıflandırılmasıyla elde
> edilmelidir — yukarıdaki dağılım §5 modül tablosundan türetilmiş
> **yaklaşıktır (±3 tolerans)**. Kesin sınıflandırma için bir sonraki
> sprint başlangıcında her bulgu satırı kategori etiketiyle CSV'ye
> indirilecek (sahip: QA + Backend platform; tarih: hardening sprint
> kickoff).

---

## 4) Pilot-blocking vs non-blocking classification

P2/REVIEW kalemlerinin **hiçbiri** pilot-blocking değildir; çünkü
pilot-blocking eşik P0 veya P1'dir ve her ikisi de sıfırdır. Yine de
"pilot süresinde gözle takip edilmeli" ve "pilot için tamamen safe" iki
sınıfına ayırıyoruz — pilot ekibe iletilecek watch list bu sınıflandırmaya
göre üretilir.

### Pilot-watch (operasyonda yan yana izlenmeli — 13 kalem)

Pilot'u **engellemez** ama pilot operatöre `monitoring runbook`a (`docs/REPLIT_OPS_CHEATSHEET.md`) ek olarak özel takip notu çıkarılır.

| Modül | Kalem | Watch sebebi |
|---|---|---|
| `ops_readiness` | CM outbox depth endpoint reachable değil; backup-status shape değişti; conflict queue endpoint absent | Operations dashboard sinyali eksik — manuel Atlas/Sentry takibi gerekli |
| `cm_exely_webhook` | Valid-payload + cancellation idempotency coverage gap | Webhook secret stres env'de unset; pilot'ta `EXELY_*` envler set olduğundan production-OK ama spec coverage'ı eksik |
| `cm_hotelrunner_webhook` | Signed-path coverage gap (`HOTELRUNNER_WEBHOOK_SECRET` unset) | Aynı — pilot env'de secret var, ama suite'te boşluk |
| `cm_outbox` | Active idempotency coverage gap — secret unset | Aynı |
| `night-audit` | C — 200 unresolved exception sample | Pilot night audit operatör dashboard'da takip etmeli |
| `housekeeping` | D2 — OOO transition guard inconclusive (0 oda BLOCKED durumunda) | HK state state-machine'in OOO branch'i suite'te exercise edilmiyor; pilot manual workflow OK |
| `folio-mass` | C4 — sample folio'larda `charges[]` boş | Pilot folio batch'i sağlam; sadece test sample tüketildi |
| `graphql_isolation` | Introspection 2xx (production'da disable önerisi) | Resolver tenant_id filtresi (`schema.py:328`) leak engellemiyor — sadece attack surface keşif ücretsiz |
| `finance_reports_currency` | B — currency convert 0/2 (rate hard floor OK) | Rate-card seed eksik |
| `ai_pricing` | recommend-rates 10s timeout | Stres env AI service flaky/timeouted — dry-run only |
| `messaging` | endpoint=/api/messaging/settings 404 | Messaging module pilot'ta deployment-dependent |
| `webhook_admin_dlq` | f8ah_setup koşulu altında | Operations admin DLQ probe |
| `eod_report` | F8AH cross-property rollup smoke | Veri seti az; production-ok |

### Pilot-safe (zero pilot impact — 47+ kalem)

By-design RBAC blocks, B2B agency seed eksikliği, MICE / CRM stres
admin rolüne kapalı surface'lar, WebSocket endpoint stres env'de
mount edilmediği için skipped. Bunlar **pilot operatörüne hiçbir şey
ifade etmez** — sadece backend hardening backlog'a girer.

---

## 5) Module-by-module P2 table

Aşağıda reporter artifact modül tablosundan **`REVIEW + SKIP > 0`**
filtresi uygulanmış modüller listelenir; tüm sayımlar artifact ground
truth'tan birebir alınmıştır. "P2 sebep" sütunu, reporter `reason=`
alanından türetilmiştir.

| Modül | PASS | REVIEW | SKIP | Toplam | Kategori | P2 sebep (özet) |
|---|---:|---:|---:|---:|:---:|---|
| `accommodation_tax` | 37 | 0 | 3 | 41 | A | RBAC stres-rolüne kapalı |
| `admin_rbac` | 5 | 0 | 4 | 9 | B | `/api/admin/tenants` 404 — endpoint not deployed (stres env) |
| `ai_noshow_risk` | 23 | 0 | 1 | 24 | C | no stress bookings (data-state) |
| `ai_pricing` | 15 | 0 | 3 | 18 | B | recommend-rates 10s timeout, network_error |
| `b2b_api` | 8 | 0 | 10 | 18 | C | agencies_list_len=0 — seed agency yok |
| `bulk-seed-500` | 11 | 1 | 0 | 12 | D | outbox_no_unexpected — outbox endpoint yok, manuel doğrula |
| `cm_exely_webhook` | 14 | 3 | 0 | 17 | B | EXELY_WEBHOOK_SECRET unset, valid-payload + cancellation idempotency coverage gap |
| `cm_hotelrunner_webhook` | 15 | 1 | 0 | 16 | B | HOTELRUNNER_WEBHOOK_SECRET unset, signed-path coverage gap |
| `cm_outbox` | 16 | 1 | 0 | 17 | B | secret unset, active idempotency gap |
| `crm_offers` | 4 | 0 | 4 | 8 | A | `/api/mice/accounts` 403 rbac_denied |
| `cross_tenant_pentest` | 8 | 0 | 1 | 9 | D | sample assertion |
| `export_artifact_idor` | 8 | 0 | 1 | 9 | C | hr_payroll_run pilot_list_empty (len=0) |
| `finance_reports_currency` | 5 | 2 | 0 | 7 | C | currency convert 0/2 — rate seed eksik |
| `folio-mass` | 9 | 9 | 0 | 18 | D | charges[] boş + payment yok (data-state) |
| `full_24h` | 22 | 7 | 1 | 30 | A+D | full-day simulation review steps |
| `gates` | 9 | 2 | 0 | 11 | — | env contract REVIEW |
| `graphql_isolation` | 16 | 1 | 0 | 17 | B | introspection 2xx; resolver filter OK |
| `hr_rbac_pii` | 4 | 0 | 7 | 11 | A | team_create_all_fail (per-role 404) |
| `hr_shift_coverage_planning` | 9 | 2 | 0 | 11 | D | coverage planning REVIEW |
| `housekeeping` | 14 | 2 | 1 | 17 | D | D2 OOO guard inconclusive |
| `identity_reporting_dryrun` | 11 | 1 | 0 | 13 | B | KBS_TEST_MODE prefix guard not enforced (env off) |
| `kvkk_retention` | 11 | 0 | 2 | 14 | A | RBAC/by-design |
| `messaging` | 7 | 1 | 0 | 8 | B | `/api/messaging/settings` 404 |
| `mice_events` | 1 | 1 | 4 | 6 | A | spaces 403 (A/B/C/D skipped) |
| `mice_execution` | 4 | 0 | 3 | 7 | A | rbac_denied |
| `mice_opportunities` | 2 | 0 | 4 | 6 | A | sales-catering 403 |
| `notification_batch` | 4 | 0 | 3 | 7 | B | DISABLE_EXPO_PUSH guard, messaging endpoint absent |
| `ops_readiness` | 11 | 1 | 0 | 12 | B | backup-status shape, CM outbox depth, conflict queue endpoint reachable değil |
| `payment_pos_reconciliation` | 12 | 0 | 3 | 16 | B | pos_tables_list http=404, manual transaction idempotency probe skipped |
| `pos_deep_lifecycle` | 33 | 1 | 0 | 35 | D | transfer happy_path 422 (gap documented) |
| `public_kvkk` | 11 | 1 | 1 | 13 | A | RBAC step |
| `public_nps` | 15 | 1 | 0 | 16 | D | NPS review step |
| `public_token_rotation` | 4 | 0 | 3 | 7 | B | `/api/rooms` 404, digital-key 404 |
| `reports_export` | 21 | 1 | 0 | 22 | D | dashboard_kpi review |
| `reservation_deep` | 11 | 4 | 2 | 17 | B | waitlist promote 404, city ledger transfer pre-req yok |
| `reservation-lifecycle` | 14 | 1 | 0 | 15 | D | review step |
| `revenue_management` | 53 | 1 | 2 | 57 | A+D | RMS review + RBAC |
| `settings_audit` | 4 | 0 | 5 | 9 | B | admin_tenants probe 404 |
| `spa_operations` | 5 | 0 | 1 | 7 | A | services/therapists/rooms 403 (catalog module-blocked) |
| `twofa_lifecycle` | 27 | 1 | 0 | 28 | D | lifecycle review step |
| `vcc_pci_compliance` | 10 | 0 | 1 | 12 | A | RBAC |
| `ws_tenant_isolation` | 4 | 0 | 3 | 7 | B | ws_endpoint_404 |

**Toplam:** 41 modül (REVIEW + SKIP > 0). Geri kalan 44 modül PASS-only
(REVIEW=0 SKIP=0).

**Findings-only modüller (P2 var ama step PASS-only):** Bazı modüller
yukarıdaki tabloya girmez çünkü tüm adımları PASS, ancak yine de
reporter `recFinding('P2', …)` ile bulgu kaydetmiştir. Bunlar §7'de
"Missing endpoint gaps" altında listelenir:

- `inventory_transfer_procurement` (21 PASS / 0 REVIEW / 0 SKIP) —
  P2: warehouse-transfer endpoint not implemented + supplier `credit_limit`
  field not modeled (bkz. E9, E10).
- `hr_shift` (14 PASS / 0 REVIEW / 0 SKIP) — P2: swap consent
  RBAC-blocked (caller ≠ target_staff email, intentional; §8'de
  by-design olarak işaretli).

---

## 6) Fixture gaps

Stres tenant'a seed edilmesi gereken ama bu run'da eksik kalan
fixture'lar. Doğru seed eklendiğinde, ilgili P2'ler doğrudan PASS'e
geçecektir.

| # | Fixture | Etkilenen modüller / spec | P2 → PASS dönüşümü için yapılacak | Sahip |
|---:|---|---|---|---|
| F1 | **B2B agency seed** | `b2b_api` (10 SKIP), `41B-b2b-subrouter-matrix` | `bulk-seed-500` factory'sine stress-prefixed agency + scope set ekle; idempotent cleanup | Backend platform |
| F2 | **POS recipe / BOM seed** | `pos_kds_inventory` (inventory deplete happy + concurrent close skip) | `bulk-seed-500`'e 5–10 recipe + ingredient BOM ekle | POS team |
| F3 | **Currency rate-card seed** | `finance_reports_currency` B | Default EUR/USD rate row stress tenant'a yaz | Finance team |
| F4 | **City ledger / open folio seed** | `reservation_deep` city-ledger transfer pre-req yok; `payment_pos_reconciliation` open folio smoke | 1 open folio + 1 city-ledger account seed | Finance team |
| F5 | **Spa catalog seed (services / therapists / rooms)** | `spa_operations` catalog probe 403 → 200 (seed varsa RBAC by-design ayrı incele) | Stress-tenant'a 3 service + 2 therapist + 2 spa room seed | Spa team |
| F6 | **Reservation digital-key seed** | `public_token_rotation` B (digital-key 404) | Reservation create akışına opsiyonel digital-key issue adımı | Guest platform |
| F7 | **HR per-role test user seed** | `hr_rbac_pii` (7 SKIP — front_desk role team_create 404) | Stress tenant'a front_desk + housekeeping + manager test user'ları seed | HR platform |
| F8 | **Pilot HR payroll run seed** | `export_artifact_idor` (hr_payroll_run pilot_list_empty) | Pilot tenant'a immutable test payroll_run seed (cleanup-safe) | HR platform |

---

## 7) Missing endpoint gaps

Stres env'de **endpoint yok** ya da **observability contract gap**. Bunlar
backend mount / observability ekleme işidir. Hiçbiri pilot-blocking
değildir çünkü pilot env'inde endpointler mount edilmiş olabilir; ama
suite coverage'ı için backend follow-up gerekir.

| # | Endpoint | Status | Etkilenen | Aksiyon |
|---:|---|---|---|---|
| E1 | `/api/admin/tenants` | 404 (stres env mount değil) | `admin_rbac` (9), `settings_audit` (9) — toplam 14 SKIP | Stres env'de admin tenant probe route'unu mount et veya spec'i `super_admin_baseline_alt` ile yenile |
| E2 | CM outbox depth observability endpoint | reachable değil | `ops_readiness` x3 | `/api/admin/cm/outbox/depth` veya benzeri observability endpoint ekle |
| E3 | CM conflict queue endpoint | reachable değil | `ops_readiness` | Conflict queue depth `/api/admin/cm/conflict-queue/depth` endpoint |
| E4 | Backup-status shape değişti | contract drift | `ops_readiness` | Yeni shape için spec adapter; backward-compat yoksa spec güncelle |
| E5 | `/api/folios?limit=50` | 404 | `payment_pos_reconciliation` IDOR list probe | Mount veya stress alias |
| E6 | `/api/folio-charges?limit=50` | 404 | aynı | Aynı |
| E7 | `/api/messaging/messages?limit=50` + `/api/messaging/settings` | 404 | `messaging`, `notification_batch` | Stres env'de messaging module mount |
| E8 | `/api/rooms` | 404 stres env'de | `public_token_rotation` | Public room read endpoint mount |
| E9 | Warehouse transfer endpoint | not implemented | `inventory_transfer_procurement` (P2) | Backend feature work — outside current sprint |
| E10 | Supplier `credit_limit` field | not modeled | `inventory_transfer_procurement` (P2) | Pydantic schema + Mongo migration |
| E11 | F&B order send endpoint (MICE execution D) | absent | `mice_execution` | F8C-v2 backlog item |
| E12 | WebSocket endpoint | 404 stres env | `ws_tenant_isolation` (3 SKIP) | WS server mount in stress env or document as production-only |
| E13 | MICE accounts `/api/mice/accounts` | 403 rbac_denied | `crm_offers` (4) | RBAC-by-design — by-design accept VEYA stress admin'e MICE rolü ekle |
| E14 | KBS_TEST_MODE prefix guard | env off → 404 | `identity_reporting_dryrun` | Stres env'de `KBS_TEST_MODE=true` set et |

---

## 8) Module-blocked surfaces (by design)

Aşağıdaki modüller stres admin rolüne **kasten kapalı**dır. Pilot
ortamında ilgili role sahip kullanıcılar erişebilir. Bu kalemler
"suite blind spot" değil, "stres admin role-scope dışı"dır.

| Modül | RBAC sebep | Spec'in davranışı | Karar |
|---|---|---|---|
| `mice_events` | spaces 403 — sales-catering rolü yok | A/B/C/D skip + final invariants PASS | **Doctrine: out of scope** — alternatif role spec'i eklenebilir (`98-mice-as-sales-manager.spec.js`) |
| `mice_opportunities` | sales-catering 403 | A/B/C/D skip | Aynı |
| `mice_execution` | rbac_denied | A/B/C skip, D F&B endpoint absent (E11) | Endpoint mount + alt role |
| `crm_offers` | mice/accounts 403 | 4 SKIP | Alt role veya scope grant |
| `hr_rbac_pii` | per-role test user 404 (F7) | team_create_all_fail | Fixture F7 ile çöz |
| `notification_batch` | DISABLE_EXPO_PUSH guard + messaging endpoint absent | 3 SKIP | E7 + env policy |
| `spa_operations` | services/therapists/rooms 403 + catalog seed yok (F5) | catalog module-blocked | F5 + RBAC review |
| `accommodation_tax` | 3 SKIP RBAC | by-design | Spec'i `tax_officer` role alternatifi ile |
| `kvkk_retention` | 2 SKIP RBAC | by-design | Compliance officer role |
| `vcc_pci_compliance` | 1 SKIP RBAC | by-design | Cashier_supervisor role |
| `hr_shift` swap consent | caller ≠ target_staff email (intentional) | 5/5 consent_perm_fail | By-design — REVIEW informational; spec'i consent flow için target_staff token ile çalıştırılacak alt-test ekle |

---

## 9) Recommended next hardening sprint

Hedef: **GO WITH WATCH → GO** geçişini sağlamak. Tahmini efor 5–8 iş günü
(paralel sahiplikle 3–4 günde sıkıştırılabilir). Sprint sonunda yeniden
Full Stress Suite koşulur; başarı kriteri `P2 ≤ 20 ve REVIEW ≤ 15`
(saf GO için 0/0 ama bu sprint kapsamında değil).

### Sprint backlog (priority order)

| Sıra | İş kalemi | Kategori | Kazanç (tahmini P2/REVIEW kapatma) | Efor (gün) | Sahip |
|---:|---|---|---:|---:|---|
| 1 | **F1**: B2B agency seed factory | Fixture | 10 SKIP + 2 P2 = 12 | 0.5 | Backend platform |
| 2 | **F7 + F8**: HR per-role + payroll seed | Fixture | 7 SKIP + 1 P2 = 8 | 1.0 | HR platform |
| 3 | **F2**: POS recipe/BOM seed | Fixture | 2 P2 = 2 | 0.5 | POS team |
| 4 | **F3 + F4**: Finance fixtures (rate-card + open folio + city ledger) | Fixture | 4 P2 = 4 | 0.5 | Finance team |
| 5 | **F5 + F6**: Spa catalog + digital-key seed | Fixture | 1 SKIP + 3 P2 = 4 | 1.0 | Guest platform |
| 6 | **E1 + E2 + E3 + E4**: Admin/ops observability endpoints + backup-status adapter | Endpoint | 14 SKIP + 3 P2 = 17 | 1.5 | Backend platform |
| 7 | **E5 + E6 + E7 + E8**: Messaging + folios + rooms route mount | Endpoint | 4 P2 = 4 | 1.0 | Backend platform |
| 8 | **E14**: `KBS_TEST_MODE=true` stres env (env-secret) | Env | 1 P2 | 0.1 | DevOps |
| 9 | **GraphQL introspection disable in production stress env** | Hardening | 1 P2 | 0.2 | Backend platform |
| 10 | **CM webhook secret stres env provision** (`EXELY_WEBHOOK_SECRET`, `HOTELRUNNER_WEBHOOK_SECRET`) | Env | 5 REVIEW | 0.2 | DevOps |
| 11 | **MICE/CRM alt-role spec'leri** (`98-mice-as-sales-manager`, vb.) | Spec | 28 SKIP → PASS-as-by-design | 1.5 | QA |
| 12 | **HR shift swap consent target-staff alt-test** | Spec | 5 consent_perm_fail | 0.5 | HR + QA |

**Tahmini kapatma:** ~60 P2 / 30+ REVIEW (sprint sonunda **GO** verdict'e
yakınsama beklenir; tam GO için backlog item #11 ve #12'nin spec write-up'ı
tamamlanmalı).

### Doctrinal constraints (sprint boyunca değişmez)

- **P2 → PASS downgrade YASAK.** Her kalem **gerçek seed/route/role**
  eklenerek kapatılır. Spec assertion gevşetme YASAK.
- **Skip-as-pass YASAK.** Module-blocked SKIP açıkça doctrine kararı
  ile (out-of-scope) işaretlenmedikçe PASS sayılmaz.
- **Pilot mutation = 0 / external_calls = []** her run'da invariant.
- **Architect review** her sprint sonunda zorunlu.

---

## 10) Sales / pilot interpretation

**Pilot otel cümlesi (paylaşıma uygun):**

> Syroce PMS'in 84 spec / 556 test'lik genişletilmiş operasyonel stres
> paketi tek seferde yeşil geçti (Run #143, 2026-05-26). Sıfır başarısız
> test, sıfır kritik (P0) ve sıfır yüksek-öncelikli (P1) bulgu;
> pilot otel verisine tek bir bayt değişiklik yok (`pilot_drift=0`);
> gerçek SMS, e-posta, OTA veya ödeme çağrısı yok
> (`external_calls=[]`). 60 informational not (P2) ve 1 düşük öncelikli
> not (P3) backend takip listesinde — pilot operasyonunu engellemez,
> sürekli iyileştirme backlog'una alınmıştır.

**Yatırımcı / stratejik ortak cümlesi (paylaşıma uygun):**

> Run #143 baseline'ı **GO WITH WATCH** verdict'iyle yeşil — bu, F8
> stres-suite doktrinimizde kabul edilen yeşil sonuçtur (saf "GO" ek
> bir alt-küme şartıdır: P2 ve REVIEW'in de sıfırlanması). Kritik
> güvenlik invariantları (cross-tenant izolasyon, IDOR, kasa,
> retention, 2FA brute-force throttle) **PASS**. Bir sonraki hardening
> sprint'i (F1–F12, 5–8 gün) sonunda P2 backlog'u yarıdan fazla
> kapatılarak saf **GO**'ya yakınsayacaktır.

**Anti-overclaim notları:**

- "**GO**" denmez. Verdict **GO WITH WATCH**'tır.
- "**Bug yok**" denmez. **P0=P1=0** denir; P2=60 / P3=1 backlog'tadır.
- "**Pilot için kusursuz**" denmez. "Pilot operasyonunu engelleyen
  bulgu yok; sürekli iyileştirme backlog'u açık" denir.
- "**Tüm endpointler test edildi**" denmez. "84 spec / 556 test
  kapsadı; module-blocked / not-deployed surface'lar §7 ve §8'de
  listelenmiştir" denir.

---

## Referanslar

- Drill report:
  [`docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md`](./drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md)
- Baseline tablo:
  [`docs/STRESS_TEST_ROADMAP.md`](./STRESS_TEST_ROADMAP.md) §
  Latest verified baseline (2026-05-26)
- Pilot trust narrative:
  [`docs/PILOT_TRUST_NARRATIVE.md`](./PILOT_TRUST_NARRATIVE.md)
- Coverage gap (paralel doküman, fixture/endpoint detayları):
  [`docs/STRESS_COVERAGE_GAP_REPORT_20260526.md`](./STRESS_COVERAGE_GAP_REPORT_20260526.md)
- Ops cheat-sheet:
  [`docs/REPLIT_OPS_CHEATSHEET.md`](./REPLIT_OPS_CHEATSHEET.md)
- ADR'lar:
  [`docs/adr/2026-05-f8ah-ops-surface-smoke.md`](./adr/2026-05-f8ah-ops-surface-smoke.md) ·
  [`docs/adr/2026-05-f8x-f8aa-compliance-money-safety.md`](./adr/2026-05-f8x-f8aa-compliance-money-safety.md) ·
  [`docs/adr/2026-05-f8r-f8w-hardening.md`](./adr/2026-05-f8r-f8w-hardening.md)
- Reporter artifact: Run #143 CI artifact (attached_assets,
  2026-05-27 reporter dump).

---

*Son güncelleme: 2026-05-27. Baseline değiştiğinde bu doküman da
revize edilir.*
