# Stress Test Roadmap (F8 Serisi)

**Hedef:** Tüm PMS modül yüzeylerini sırayla GitHub Actions stress CI'ya
sokmak — pilot tenant'a mutation yok, gerçek dış servis çağrısı yok,
external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH.

## Latest verified baseline (2026-05-24) ✅ GREEN — F8R–F8W included

> **Bu satır resmi baseline'dır** — yeni geliştirmeler bu green run'a
> karşı regression test'ler. Detay raporlar:
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
| F8L  | Channel Manager + Webhooks (Exely / HotelRunner / Outbox / SXI bus)     | 50 / 51 / 52              | **DONE** — Task #195 merged (2026-05-19) — 22 test (architect-iter-4): Exely IP+payload+tenant-injection+replay + HotelRunner HMAC sig contract+surface coverage+logs scope + Outbox status/events/RBAC + Conflict Queue cross-tenant scope. **Önceki tabloda IN_PROGRESS görünmesi stale idi — DONE doğru durum.** | TBD                                                       |
| F8M  | GraphQL + B2B API (resolver isolation / API key scope)                  | 40 / 41                   | **DONE** — Task #194 merged (2026-05-19) — 11 test, GraphQL introspection + resolver isolation + cross-tenant injection + B2B api-key lifecycle/scope/revocation | TBD                                                       |
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

### F8X — E-invoice / Finance Document Forbidden Path (önerilen)
- **Spec:** `28B-efatura-forbidden-source-scan.spec.js` (planlandı, henüz yok)
- **Kapsam:** F8E'de `/efatura/*` ve `/invoices/{id}/generate-efatura`
  YASAK; source-scan ile bu yolların stress spec'lerinde çağrılmadığını
  doğrula · invoice preview/export dry-run · external_calls=[] post-batch.
- **Neden:** Gerçek GİB dispatch risk; F8E gotcha not'unda "bilinçli
  dışarıda" yazıyor ama otomatik regression koruması yok.

### F8O v2 — AI prompt PII redaction (önerilen)
- **Kapsam:** AI prompt PII redaction snapshot · AI recommendation audit
  trail · human approval required guard · AI response explainability alanı
  zorunlu · AI output deterministic schema validation.

### F8K v2 — QR token rotation deep (önerilen — F8Q § 63 başlangıç)
- ✅ Tamper / cross-tenant / staff PII bulk — F8Q § 63 (DONE).
- **Eksik:** secret rotate old token grace behavior · revoked token TTL
  · raw token/secret log leak guard · audit log emit.

### F8F v2 — Warehouse Transfer (önerilen)
- **Kapsam:** warehouse A → warehouse B transfer · transfer reversal ·
  partial receipt · supplier credit limit · purchase order cancellation ·
  stock valuation after movement.
- **Neden:** F8F § 70/71 bilinçli olarak transfer'i scope dışı bıraktı
  (multi-target probe contract'a uygun değil); canlı işletmede depo
  transferi önemli.

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
