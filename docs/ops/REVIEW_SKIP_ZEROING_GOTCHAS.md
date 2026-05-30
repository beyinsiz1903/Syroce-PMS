# REVIEW/SKIP Zeroing & Reduction — GOTCHAS Archive

Bu dosya, `replit.md`'den taşınan uzun REVIEW/SKIP Zeroing (Wave 6–9) ve REVIEW/SKIP
Reduction (Package A+B → F) detay kayıtlarının arşividir. Tek-satırlık özetler ve
mevcut durum `replit.md`'de; baseline zinciri `docs/baselines/BASELINE_CHAIN.md`'de;
paket damıtımı `docs/drill_reports/20260530_review_skip_packages_ab_to_f_summary.md`'de.

Doktrin (her fazda mutlak): pilot mutation=0 · external_calls=[] · failedTests=0 ·
P0=P1=0 · verdict ≥ GO WITH WATCH · assertion gevşetme YOK · skip-as-pass YOK ·
kör-seed YASAK · baseline pointer operatör onayı olmadan TAŞINMAZ · full stress agent
tarafından dispatch EDİLMEZ (CI-deferred).

---

## REVIEW/SKIP Zeroing — Wave 6 (env/secret/test posture)

Hedef 5 alanda backend kodu zaten fail-closed/doğru; REVIEW'lar stres env posture
eksiği (bug değil). Repo: `stress.yml` runner-side `HOTELRUNNER_WEBHOOK_SECRET =
secrets.STRESS_HOTELRUNNER_WEBHOOK_SECRET` (unset → spec honest REVIEW). Operatör (repl
dışı, devops): stres backend AYNI secret + `EXELY_IP_WHITELIST`=runner-IP (tercih) +
`KBS_TEST_MODE=1` + `GRAPHQL_INTROSPECTION=false`. Exely KARARI (Murat 2026-05-30):
`ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK` KULLANILMAZ; whitelist yoksa stres-only çok-koşullu
`EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` (backend kod görevi, ayrı tur; prod
fail-closed 503 değişmez). PROD gerçek secret/whitelist; fail-closed korunur.
Runbook+validation: `docs/drill_reports/20260529_review_skip_wave6_candidate.md`;
envanter: `docs/drill_reports/20260529_review_skip_zeroing_inventory.md`. Baseline #162
pointer TAŞINMAZ; targeted spec PASS CI-deferred.

## REVIEW/SKIP Zeroing — Wave 7 (seed/data-state)

Seed kodu birebir okununca 14 item'dan yalnız 2'si gerçek+güvenli+endpoint-bağımsız
seed gap; gerisi zaten seedli (duplicate-seed=false-green → EKLENMEDİ) ya da
endpoint/env/RBAC blocker (reclassify). DONE: (1) b2b `agencies` stres seed
(`_build_agency_docs` 5 doc + STRESS_COLLECTIONS + orphan-scrub; `name`≥2
placeholder-uyumlu) → 41B P2×10; (2) pilot `payroll_runs` IDOR fixture
(`_ensure_payroll_run`, `status="fixture"` partial-unique-safe + finalized değil,
`period_month="2099-01"`, residue-cleanup dokunmaz) → 91 SKIP×1. KÖR-SEED YASAĞI
KANITI: `payment_pos_reconciliation` OPEN-shift seed REDDEDİLDİ (`_build_f8e_docs`
bilinçli `closed`; `uniq_tenant_open_shift` + spec self-open; OPEN seed yeşil spec'i
kırardı). Reclassify: 6→W8 endpoint, 2→env-gate, vcc→W9 RBAC, hr_rbac_pii→W8.
CI-DEFERRED (stres/pilot tenant lokal seedli değil, fail-closed), skip-as-pass YOK.
Aday: `docs/drill_reports/20260530_review_skip_wave7_candidate.md`. Baseline #162
pointer TAŞINMAZ.

## REVIEW/SKIP Zeroing — Wave 8 (endpoint/mount/surface)

Canlı read-only GET probe (stres ADMIN token, Atlas; mutasyon yok) ile ölçüldü:
**ENDPOINT_NOT_DEPLOYED büyük ölçüde MİSCLASSIFICATION**. Hedef "404" yüzeyleri
deploy+mount'lu; 404 kök sebep (1) **platform-super-admin guard fail-closed 404**
(`require_super_admin_guard(not_found=True)` super_admin olmayana 403 değil 404 → varlık
gizleme; stres admin bilinçli tenant-scoped, platform DEĞİL → `/api/admin/tenants`,
`/api/admin/feature-flags`, `/api/webhooks/status`+`/dlq`, `/api/outbox/status`
doğru-404; 2xx yapmak=auth weakening=YASAK → kategori 8 by-design), (2) **spec
path-drift** (gerçek: `/api/messaging-center/*`, `/api/finance/folio/list`,
`/api/infra/...`), (3) **gerçek absent roadmap/deploy-only** (`pos_tables` list, waitlist
`/promote`, mice F&B order-send, QR rotation HTTP yok=`ROOM_QR_SECRET` env). **Mount
edilecek eksik ürün yüzeyi YOK → kör stub EKLENMEDİ.** DONE (tek kod = test-drift):
`45-notification-batch` 6 path `/api/messaging`→`/api/messaging-center` +
`activity-feed`→`activity` + 3 POST body `to:`→`recipient:` (SendReq alanı);
moduleBlocked SKIP×3+P2×3 → güvenlik assertion'ları (no 5xx / cross-tenant leak / PII
mask / external_calls=[]) gerçek-koşar (güçlendirme, fake-green değil; sends 4xx olsa
bile serverErr=0 hard-assert tutar). `node --check` PASS, leftover legacy path yok.
CI-DEFERRED doğrulama. Aday: `docs/drill_reports/20260529_review_skip_wave8_candidate.md`.
Baseline #162 pointer TAŞINMAZ.

## REVIEW/SKIP Zeroing — Wave 9 (RBAC/PII/ürün-sözleşmesi)

8 yüzey teknik gap değil ürün/RBAC sözleşme kararı; dürüstçe sınıflandırıldı, yalnız
minimal güvenli düzeltmeler targeted testlerle (21 PASS). Run #162 pointer TAŞINMADI;
full stress KOŞTURULMADI. DONE: (1) messaging `/activity` recipient PII mask
(`view_guest_list` gate, düşük-yetkili sızıntı kapandı), (2) folio `void_payment` RBAC
`post_payment`→`void_payment` (FRONT_DESK istenmeyen void yetkisi kalktı), (3) CRM
`companies.tax_number` tenant-içi tekil→409 (değer varken, whitespace-only None, tek
insert path), (4) NPS `submit_survey_response` (survey,booking) UTC-gün başına tek→409
(booking_id'siz muaf). CONFIRM by-design: GraphQL introspection prod/stress-off + dev
opt-in; KVKK anonymize+audit+fail-closed, hard-delete yok kasıtlı. DEFER scoped
follow-up: e-Fatura VKN/TCKN `customer_type`-zorunlu (geriye-uyum+migration); revenue
`dry_run` kill-switch (çok-endpoint). Aday:
`docs/drill_reports/20260530_review_skip_wave9_candidate.md`. Baseline #162 pointer
TAŞINMAZ.

---

## REVIEW/SKIP Reduction — Package A+B (Run #167 baseline)

ENV/posture + güvenli seed/data-state. KRİTİK mimari ayrım: stress suite iki ortam — CI
runner (`stress.yml`, sadece test-side değerler) vs stress BACKEND deployment
(operatör-kontrollü, repl dışı; KBS_TEST_MODE/GRAPHQL_INTROSPECTION/EXELY_*/HOTELRUNNER
env BURADA okunur). Kör runner-wiring backend'i etkilemez=fake-green=EKLENMEZ. Run #167
pointer TAŞINMAZ; full stress KOŞTURULMADI; CI-deferred (backend pytest 14 PASS + spec
`node --check`). DONE A1: Exely `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing`
çok-koşullu fail-closed test-auth gate (5 koşul AYNI ANDA: mode + non-prod +
`E2E_EXTERNAL_DRY_RUN` + `E2E_ALLOW_DESTRUCTIVE_STRESS` + `E2E_STRESS_TENANT_ID`);
yasaklı `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK`'tan AYRI; prod fail-closed 503 değişmez;
tenant server-side HotelCode→exely_connections (pilot drift imkânsız); W6-deferred
kapandı (`test_exely_test_auth_mode.py`). DONE B1: spec 98 idempotency testi izole stress
vardiya self-open/close (`uniq_tenant_open_shift` guard'lı, pilot mutation yok).
RECLASSIFY (dokunulmadı): A2 KBS / A3 GraphQL / A4 HotelRunner = operatör backend-env
(kod yok); B2 24h scarcity→test-drift, B3 folio-mass→serializer surface (kör seed YASAK);
diğerleri→Paket C. Envanter+aday:
`docs/drill_reports/20260530_review_skip_reduction_package_ab_{inventory,candidate}.md`.

## REVIEW/SKIP Reduction — Package C (Run #168 baseline)

Ürün-sözleşme/uyum kararları. 8 hedef kod-kanıtıyla sınıflandı; baseline #168 pointer
TAŞINMAZ, full stress KOŞTURULMADI (operatör dispatch), CI-deferred targeted pytest.
**Tek kod = e-Fatura compliance parite**: ortak yardımcı `_normalize_customer_tax_number`
(`backend/routers/finance/accounting.py`) tek doğruluk kaynağı —
`InvoiceCreate.customer_tax_id` paritesi (10=VKN/11=TCKN digit; strip→boş=None;
ValueError→422); `AccountingInvoiceCreateRequest` `field_validator` + ham-dict
`update_accounting_invoice` (post-create malformed yazım kapatıldı) ikisi de çağırır;
additive/geriye-uyumlu; from-folio yolu `customer_tax_number` KABUL/SET ETMEZ →
dokunulmadı (legacy retroaktif 422 yok); `test_invoice_tax_id_contract.py` +13 case →
26/26 PASS. CONFIRM-BY-DESIGN (kod yok): KVKK anonymize-only+audit+fail-closed
(hard-delete kasıtlı yok), NPS 409 dedup (Wave 9; `test_nps_duplicate_guard.py` 3/3),
Admin super_admin-guard fail-closed 404 (Wave 8; 2xx=auth-weakening YASAK), agency
contract state machine zaten tam. OPERATOR-ENV: GraphQL introspection backend fail-closed
doğru (`_introspection_enabled`); stres backend `SENTRY_ENVIRONMENT=stress` veya
`GRAPHQL_INTROSPECTION=false` set etmeli (yeni env yok). SCOPED-FOLLOW-UP (büyük/breaking,
zorlanmadı): revenue global dry_run kill-switch (tenant shadow_mode/write_enabled zaten
fail-safe), B2B per-subrouter scope (key scope alanı+13 router+migration),
corporate-contract approval state machine, e-Fatura `customer_type` zorunlu.
external_calls=[], pilot mutation=0, RBAC grant yok. Envanter+aday:
`docs/drill_reports/20260530_review_skip_package_c_{inventory,candidate}.md`.

## REVIEW/SKIP Reduction — Package D (Run #168 baseline)

Endpoint/surface/module-blocked. 8 yüzey kod-kanıtıyla sınıflandı; baseline #168 pointer
TAŞINMAZ, full stress KOŞTURULMADI (operatör dispatch), no mobile/F10, no backend kod
değişikliği. **Tek güvenli düzeltme = spec path-drift**: `96-cross-tenant-pentest.spec.js`
`messages` yüzeyi `/api/messaging/messages` (backend'de YOK→404→surface blocked→leak scan
vacuous) → `/api/messaging/conversations` (gerçek liste, `domains/guest/messaging/router.py`
prefix `/api`; stress token erişimi `13-messaging` §B ile kanıtlı; `itemArray`
`conversations` key'i zaten ele alıyor). Güvenli: `withModuleProbe` non-2xx'te graceful P2
→ FAIL riski YOK; en iyi durumda 1 P2 `surface_blocked:messages` kapanır + gerçek
cross-tenant coverage (güçlendirme, fake-green değil). KANIT: messaging
send-{email,sms,whatsapp}/conversations `/api/messaging/*` GERÇEKTEN var
(`domains/guest/messaging/router.py`), `13-messaging` drift DEĞİL. CONFIRM-BY-DESIGN (7):
admin/tenants+feature-flags+webhooks/dlq+outbox/status+global-user-create super_admin
fail-closed 404 (`require_super_admin_guard(not_found=True)`, 2xx=auth-weakening YASAK);
spa/mice EntitlementMiddleware 403+upgrade_url; public QR HMAC-gated+PII-masked;
enterprise_live WS unconditionally mounted (registry L65, 98B 404-fallback
defensive—isolation probes koşar); 31-settings-audit zaten gerçek audit path
(`/api/audit/timeline`,`/api/security/audit-logs`). ROADMAP: QR rotation env-only
(`ROOM_QR_SECRET`, HTTP route yok—kasıtlı). Stub EKLENMEDİ. `node --check` PASS.
Envanter+aday: `docs/drill_reports/20260530_review_skip_package_d_{inventory,candidate}.md`.

## REVIEW/SKIP Reduction — Package E (Run #168 baseline)

Seed/data-state/harvest. 11 yüzey 3 paralel explore + spec satır-kanıtıyla sınıflandı;
baseline #168 pointer TAŞINMAZ, full stress KOŞTURULMADI (operatör dispatch), no
mobile/F10, no backend kod, no seed eklendi, no stub, no pilot mutation. **Tek güvenli
düzeltme = harvest window (spec-only)**: `04-folio-mass.spec.js` C4 (void-charge) + C5
(void-payment) eskiden C(split,`slice(0,10)`)+C3(refund,`slice(0,10)`) ile AYNI
folios[0..4]'ü örnekliyordu → void hedefleri tüketilmiş → void path hiç koşmuyor →
vacuous `allEmpty`(C4 P2)/`allNoPay`(C5 P3). Fix: `voidSampleWindow(src)` = `slice(10,15)`
(C/C3 yıkıcı aralık 0..9'un ÖTESİ ama A charge 0..99 / B payment 0..49 yaratma aralığı
İÇİ), pool küçükse `slice(0,5)`'e fallback. By-construction güvenli: status ladder
(all403/allEmpty/allNoPay→REVIEW, 5xx→FAIL) AYNEN korunur → yeni FAIL sınıfı YOK,
assertion gevşetme YOK (self-create yapılmaz; void zaten charge varken FAIL-able'dı).
CI-deferred (seedli full-suite'de void path gerçek koşar, vacuous P2/P3 kapanır=güçlendirme).
CONFIRM-BY-DESIGN (6): finance_folio `no_created_payment_to_void` (create→void lifecycle),
notification activity feed empty (enqueue'dan AYRI yüzey, baseline'da da boş=async lag
değil, poll fayda etmez, zaten P2, FAIL etmez), VCC no booking (factory-seed bağımlılığı;
bookings-by-`stress_prefix` harvest başka yerde çalışıyor=drift değil), full_24h scarcity
(integration smoke healthy seed ister), revenue_mgmt hurdle/queue IDOR (stress self-create
yeterli; pilot IDOR probe by-design), city ledger (real flow self-create + `_build_f8e_docs`
seed). DO_NOT_TOUCH-pilot (2): payment_pos_reconciliation OPEN-shift (kör-seed YASAK,
`uniq_tenant_open_shift`, self-open doğru), accommodation_tax pilot declaration pool
(success read pilot decl ister, pilot mutation yok). ROADMAP (1+1): POS recipe/BOM seed
(Task #11 out-of-scope; cleanup destekler ama recipe seed green-spec güvenliği
doğrulanamaz=kör-seed riski→ertelendi, stub DEĞİL) + public_token rotation endpoint
(backend'de yok, env-only `ROOM_QR_SECRET`). `node --check` PASS. Envanter+aday:
`docs/drill_reports/20260530_review_skip_package_e_{inventory,candidate}.md`.

## REVIEW/SKIP Reduction — Package F (Run #168 baseline)

Frontend/UI selector & render coverage. baseline #168 pointer TAŞINMAZ, full stress
KOŞTURULMADI (operatör dispatch), no mobile/F10, no backend kod, no data-testid eklendi,
no stub, no visual redesign, no pilot mutation. **KRİTİK kapsam bulgusu:** tüm
`frontend/e2e-stress/specs/` içinde gerçek browser render
(`browser.newContext`+`page.goto`+`.locator`+TTI) yapan TEK spec =
`08-housekeeping-mass.spec.js`; diğer "UI" REVIEW/SKIP'ler API/HTTP probe (Paket D/E'de
sınıflanmış), selector DEĞİL. **Tek güvenli düzeltme = selector+route drift (spec-only)**:
`08-housekeeping-mass` FE render TTI testi `/housekeeping` (= `HousekeepingDashboard`, oda
grid'i YOK) hedefliyordu + selector whitelist
(`room-card`/`hk-room-row`/`tr[data-room-id]`/`.room-card`) grid'in gerçek testid'leriyle
hiç eşleşmiyordu → `total_rows=0` → kalıcı vacuous `noRows→REVIEW` (TTI coverage hiç
koşmuyordu). Gerçek grid: `/housekeeping-status` → `HousekeepingStatusPage` →
`HousekeepingRoomGrid` (`routes/sections/coreOperations.js` L35); container
`data-testid="housekeeping-room-grid"`, oda `data-testid="room-card-<room_number>"`
(L199), durum butonu `status-btn-<room_number>-<key>` (L235). Fix (3 spec edit,
mantık/assertion DEĞİŞMEDİ): route `/housekeeping`→`/housekeeping-status`; selector
whitelist'e `[data-testid^="room-card-"]` öne eklendi (legacy fallback korundu); mobile
transition locator'ına `[data-testid^="status-btn-"]` öne eklendi; rec endpoint notu
güncellendi. Status ladder (`noRows?REVIEW:slow?FAIL:PASS`, ROW_GATES
50<3s/200<6s/500<10s, dom<10s, first_row<8s, slow→P2) AYNEN korundu. **Şeffaf CI-deferred
risk:** grid virtualization'sız render eder (`filteredRooms.map`; spec yorumu zaten
"500-oda için virtualization gerekebilir" diyor) → seedli full-suite'te ya REVIEW→PASS
(güçlendirme) ya da gerçek 500-oda perf breach → P2+FAIL (intended detection, test-logic
regresyonu DEĞİL; Paket E architect kararıyla tutarlı). Strict-GREEN istenirse çözüm ürün
kararı (grid virtualization) / perf-gate re-baseline'dır, bu testi gevşetmek DEĞİL.
CONFIRM-BY-DESIGN (4): notification/messaging + frontdesk + admin/settings +
marketplace/POS — stress'te DOM-render spec'i yok (API probe / super-admin fail-closed
gate); browser UI-render coverage eklemek = yeni test yüzeyi = ROADMAP, selector fix
değil. `node --check` PASS. Envanter+aday:
`docs/drill_reports/20260530_review_skip_package_f_{inventory,candidate}.md`.

---

## Closing note — 2026-05-26 baseline stabilization (historical)

Run #143 official 84-spec GO WITH WATCH baseline stabilized. Stale T001–T006 plan
retired. P2/REVIEW triage moved to §11 pre-pilot decision matrix
(`docs/STRESS_P2_REVIEW_TRIAGE_20260526.md`). Sentry worker noise reduction completed
with `TransientFailureTracker` across 11 workers (architect Round-2 PASS, commit
`6f48e71`). Bu noktadan sonra yeni faz ayrı başlık altında açılacak: **Pilot Onboarding
Pack · MUST CLOSE PC1–PC4 Sprint · Sales/Investor Readiness Pack**.
