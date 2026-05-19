# Stress Test Roadmap (F8 Serisi)

**Hedef:** Tüm PMS modül yüzeylerini sırayla GitHub Actions stress CI'ya
sokmak — pilot tenant'a mutation yok, gerçek dış servis çağrısı yok,
external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH.

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

## Faz listesi ve durumlar

| Faz  | Kapsam                                                                  | Spec aralığı              | Status                                                       | ADR                                                       |
| ---- | ----------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------ | --------------------------------------------------------- |
| F8A  | Front Office / Folio / Housekeeping (day-turnover, room-move, mass, **lifecycle, night-audit**) | 02 / 03 / 04 / 05 / 06    | **DONE** — GO WITH WATCH (CI #38 / #55 PASS, tur-6..22) + **v2 push 2026-05-18** (spec 05 reservation lifecycle + spec 06 night-audit + spec 04 refund/void extension) | `docs/adr/2026-05-f8a-stress-evolution.md`                |
| F8B  | Guest Experience (QR / complaints / messaging / notifications)          | 10 / 11 / 12 / 13         | **DONE** — GO WITH WATCH (CI #55 PASS, tur-23..26)           | `docs/adr/2026-05-f8b-stress-evolution.md`                |
| F8C  | MICE / Event / Banquet / Group Operations                               | 14 / 15 / 16 / 17         | **DONE** — GO WITH WATCH (tur-5 CI YEŞİL, 2026-05-18)        | `docs/adr/2026-05-f8c-stress-evolution.md`                |
| F8D  | HR / İK / Staff / Shift / Leave / Department                            | 20 / 21 / 22 / 23         | **DONE (v1)** — GO WITH WATCH (CI yeşil, 2026-05-18); v2 backlog aşağıda | `docs/adr/2026-05-f8d-hr-staff-shift-evolution.md`        |
| F8E  | Finance / Cashier / Accounting / Invoice / City Ledger                  | 24 / 25 / 26 / 27 / 28    | **DONE v2** — GO WITH WATCH (CI #42+, 2026-05-19)            | `docs/adr/2026-05-f8e-finance-stress-evolution.md`        |
| F8F  | Inventory / Stock / Purchasing / Supplier                               | 30 / 31 / 32 / 33         | Planlandı (Task #197)                                        | TBD                                                       |
| F8G  | Sales / CRM / Offers / Contracts (F8C MICE-sales üstünde devam)         | 34 / 35 / 36              | Planlandı (Task #198)                                        | TBD                                                       |
| F8H  | Reports / Analytics / Export                                            | 40 / 41 / 42              | Planlandı (Task #199)                                        | TBD                                                       |
| F8I  | Admin / RBAC / Settings / Audit                                         | 44 / 45 / 46 / 47         | Planlandı (Task #193, ilk sıra)                              | TBD                                                       |
| F8J  | **Full 24h Hotel Simulation** — tüm modüller birlikte                   | 50 (chained scenario)     | Final — F8F-N yeşilden sonra (Task #201)                     | TBD                                                       |
| F8K  | **Guest-facing public flows** (online check-in / NPS / digital key)     | 60 / 61 / 62 / 63         | Planlandı (Task #196)                                        | TBD                                                       |
| F8L  | **Channel Manager + Webhooks** (Exely / HotelRunner / SXI bus)          | 64 / 65 / 66 / 67         | Planlandı (Task #195)                                        | TBD                                                       |
| F8M  | **GraphQL + B2B API** (resolver isolation / API key scope)              | 68 / 69 / 70 / 71         | Planlandı (Task #194)                                        | TBD                                                       |
| F8N  | **Reservation lifecycle deep** (create/modify/cancel/no-show/group)     | 72 / 73 / 74 / 75         | Planlandı (Task #200)                                        | TBD                                                       |

### F8F–F8N expansion contract (Task #192 Foundation)

Her yeni faz için aşağıdaki sözleşme zorunludur (F8A–F8E baseline'ı bozmadan ek olarak):

| Faz  | Spec dosyaları                          | Test sayısı | Risk     | Dry-run kuralı                                                                                                              | Cleanup kapsamı                                                                       | Pilot drift | external_calls |
| ---- | --------------------------------------- | ----------- | -------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------- | -------------- |
| F8F  | 30-inventory · 31-stock · 32-purchasing · 33-supplier | 4–6 | MEDIUM   | Procurement PO `approve` lokal; supplier portal push YOK (`E2E_EXTERNAL_DRY_RUN=true`)                                      | `inventory_items`, `stock_movements`, `suppliers`, `purchase_orders` (stress_prefix)  | =0          | []             |
| F8G  | 34-crm-leads · 35-offers · 36-contracts | 3–5         | MEDIUM   | CRM offer email send dry-run (Resend silent); contract e-signature provider call YOK                                        | `crm_leads`, `offers`, `contracts` (stress_prefix)                                    | =0          | []             |
| F8H  | 40-reports-finance · 41-reports-ops · 42-export | 3–5 | LOW      | Report run read-only; export PDF/XLSX in-memory, dosya yazımı yok                                                           | Yok (read-only); cache invalidation idempotent                                        | =0          | []             |
| F8I  | 44-admin-rbac · 45-settings · 46-audit · 47-user-mgmt | 5–7 | **HIGH** | RBAC negative test (403 expect); audit log read; user create/disable lokal                                                  | `users` (stress_prefix), `audit_logs` ASLA silinmez (KVKK retention)                  | =0          | []             |
| F8J  | 50-24h-full                             | 1 (chained) | HIGH     | Tüm F8 path'lerinin chained dry-run koşusu; tek spec, çok step                                                              | Önceki fazların cleanup helper'larını çağırır (composite)                             | =0          | []             |
| F8K  | 60-online-checkin · 61-nps-reviews · 62-qr-token-expiry · 63-public-ratelimit | 5–7 | **CRITICAL** | KVKK consent, ID metadata-only (binary upload YOK), digital-key issue/revoke dry-run, public RL 429 boundary | `online_checkin_submissions`, `guest_reviews`, `nps_responses`, `digital_keys`        | =0          | []             |
| F8L  | 64-cm-exely · 65-cm-hotelrunner · 66-sxi-bus-outbox · 67-webhook-signature | 5–7 | **CRITICAL** | Exely IP allowlist (literal, CIDR YOK); HMAC sig verify; OTA push CB açık, gerçek HTTP YOK         | `outbox_events` (stress_prefix), `webhook_logs`                                       | =0          | []             |
| F8M  | 68-graphql-isolation · 69-b2b-api-key · 70-b2b-rbac · 71-b2b-audit | 5–7 | **CRITICAL** | GraphQL cross-tenant query, B2B API key scope/rate-limit, n+1 + depth limit                | `b2b_api_keys` (stress_prefix), `b2b_api_audit`                                       | =0          | []             |
| F8N  | 72-reservation-batch · 73-cancel-noshow · 74-group-multiroom · 75-overbooking-waitlist | 6–8 | HIGH | F8A lifecycle deep dive; CM outbox event consistency F8L ile overlap            | `bookings`, `group_bookings`, `folios` (stress_prefix)                                | =0          | []             |

**GO/NO-GO eşiği (tüm fazlar)**: `failedTests=0`, `P0=0`, `P1=0`, `cleanup#2 idempotent`, `pilot_drift=0`, verdict ≥ `GO WITH WATCH`.

**module-blocked pattern fallback**: Her spec'te endpoint 403 / 404 / RBAC fail → `moduleBlocked=true` flag + P2 informational + A/B/C/D `test.skip()`, pilot_drift bağımsız çalışır (F8C/D/E doctrine, `withModuleProbe` helper).

**Foundation helpers (Task #192 ekledi)** — `frontend/e2e-stress/fixtures/stress-helpers.js`:
- `assertPilotDriftZero(request, stressTokens, baseline)` — pilot bookings count read-only diff, leak tespit eder.
- `assertNoExternalCallsPostBatch(...)` — tur-28 per-batch delta doctrine (mevcut, korunuyor).
- `assertPiiMasked(responseBody, fields)` — telefon/email/TC/passport gibi PII alanları masked olduğunu doğrular (KVKK / F8I / F8K / F8M kritik).
- `withModuleProbe(request, token, endpoint)` — endpoint 403/404 → `{moduleBlocked: true}` döner, spec'ler A/B/C/D step'lerini güvenle skip eder.

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
- **Rate-limit boundary**: 429 backoff var; explicit per-endpoint RL
  boundary push testi yok.
- **Tenant isolation cross-check**: bookings count spot-check seviyesinde;
  guests / folios / charges / messages / hr_staff için ayrı pen-test yok.
- **GraphQL surface** (threat-model yüksek risk): yok → F8M.
- **B2B API** (API key auth): yok → F8M.
- **Webhook endpoints** (Exely / HotelRunner IP allowlist): yok → F8L.
- **AI integration paths** (upsell / dynamic pricing / no-show risk): yok.

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
