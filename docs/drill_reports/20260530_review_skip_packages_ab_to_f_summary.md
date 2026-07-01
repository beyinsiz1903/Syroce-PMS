# REVIEW/SKIP Reduction Program — Packages A+B → F Summary

**Tarih:** 2026-05-30
**Baseline:** Run #168 GREEN BASELINE (bkz. `docs/baselines/BASELINE_CHAIN.md`).
**Durum:** A+B, C, D, E, F tamamlandı. **Tüm paketler sonrası final full stress
HENÜZ yeniden KOŞTURULMADI** — baseline pointer #168'de sabittir.

## Program doktrini (her pakette mutlak)

no fake-green · no RBAC weakening · no auth weakening · no PII exposure · no pilot
mutation (pilot_drift=0) · external_calls=[] · failedTests=0 · P0=P1=0 · assertion
gevşetme YOK · skip-as-pass YOK · kör-seed YASAK · gerçek UI failure'ı REVIEW'a
düşürme YOK · gerçek başarısız UI path'i sayım azaltmak için skip etme YOK · düz "GO"
veya "/100" iddiası YOK · mobile/F10 ayrı. Agent full stress dispatch EDEMEZ;
doğrulama targeted pytest / `node --check` / canlı read-only probe ile CI-deferred.

Her paket "tek doğruluk kaynağı" envanter + aday drill raporlarına dayanır; aşağıdaki
özetler onların damıtımıdır. Tam Wave 6–9 + paket detayları:
`docs/ops/REVIEW_SKIP_ZEROING_GOTCHAS.md`.

---

## Package A+B — ENV/posture + güvenli seed/data-state (Run #167 baseline'da başladı)

- **Kapsam:** ENV/posture düzeltmeleri + güvenli seed/data-state.
- **Kritik mimari ayrım:** stress suite iki ortam — CI runner (`stress.yml`, yalnız
  test-side değerler) vs stress BACKEND deployment (operatör-kontrollü, repl dışı;
  KBS_TEST_MODE / GRAPHQL_INTROSPECTION / EXELY_* / HOTELRUNNER env BURADA okunur). Kör
  runner-wiring backend'i etkilemez = fake-green = EKLENMEZ.
- **Kod (2):** (A1) Exely `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` çok-koşullu
  fail-closed test-auth gate (5 koşul aynı anda: mode + non-prod + `E2E_EXTERNAL_DRY_RUN`
  + `E2E_ALLOW_DESTRUCTIVE_STRESS` + `E2E_STRESS_TENANT_ID`); yasaklı
  `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK`'tan ayrı; prod fail-closed 503 değişmez; tenant
  server-side HotelCode→exely_connections. (B1) spec idempotency testi izole stress
  vardiya self-open/close (`uniq_tenant_open_shift` guard'lı, pilot mutation yok).
- **Reclassify (dokunulmadı):** A2 KBS / A3 GraphQL / A4 HotelRunner = operatör
  backend-env (kod yok); B2 24h scarcity→test-drift, B3 folio-mass→serializer surface
  (kör seed YASAK); diğerleri→Paket C.
- **Doğrulama:** backend pytest 14 PASS + spec `node --check`. Run #167 pointer TAŞINMADI.
- **Drill:** `docs/drill_reports/20260530_review_skip_reduction_package_ab_{inventory,candidate}.md`.

## Package C — Ürün-sözleşme/uyum kararları (Run #168 baseline)

- **Tek kod = e-Fatura compliance parite:** ortak yardımcı
  `_normalize_customer_tax_number` (`backend/routers/finance/accounting.py`) tek doğruluk
  kaynağı — `InvoiceCreate.customer_tax_id` paritesi (10=VKN / 11=TCKN digit; strip→boş
  =None; ValueError→422); `AccountingInvoiceCreateRequest` field_validator + ham-dict
  `update_accounting_invoice` ikisi de çağırır; additive/geriye-uyumlu; from-folio yolu
  `customer_tax_number` kabul/set etmez (legacy retroaktif 422 yok). `test_invoice_tax_id_contract.py` 26/26 PASS.
- **CONFIRM-BY-DESIGN (kod yok):** KVKK anonymize-only + audit + fail-closed (hard-delete
  kasıtlı yok); NPS 409 dedup (Wave 9); Admin super_admin-guard fail-closed 404 (Wave 8;
  2xx=auth-weakening YASAK); agency contract state machine zaten tam.
- **Operator-env:** GraphQL introspection backend fail-closed doğru; stres backend
  `SENTRY_ENVIRONMENT=stress` veya `GRAPHQL_INTROSPECTION=false` set etmeli (yeni env yok).
- **Scoped follow-up (zorlanmadı):** revenue global dry_run kill-switch; B2B per-subrouter
  scope; corporate-contract approval state machine; e-Fatura `customer_type` zorunlu.
- **Drill:** `docs/drill_reports/20260530_review_skip_package_c_{inventory,candidate}.md`.

## Package D — Endpoint/surface/module-blocked (Run #168 baseline)

- **Tek güvenli düzeltme = spec path-drift:** `96-cross-tenant-pentest.spec.js` `messages`
  yüzeyi `/api/messaging/messages` (backend'de yok→404→surface blocked→leak scan vacuous)
  → `/api/messaging/conversations` (gerçek liste). `withModuleProbe` non-2xx'te graceful
  P2 → FAIL riski yok; en iyi durumda 1 P2 kapanır + gerçek cross-tenant coverage.
- **CONFIRM-BY-DESIGN (7):** admin/tenants + feature-flags + webhooks/dlq + outbox/status
  + global-user-create super_admin fail-closed 404 (2xx=auth-weakening YASAK); spa/mice
  EntitlementMiddleware 403+upgrade_url; public QR HMAC-gated+PII-masked; enterprise_live
  WS unconditionally mounted; 31-settings-audit zaten gerçek audit path.
- **Roadmap:** QR rotation env-only (`ROOM_QR_SECRET`, HTTP route yok—kasıtlı). Stub
  EKLENMEDİ. `node --check` PASS.
- **Drill:** `docs/drill_reports/20260530_review_skip_package_d_{inventory,candidate}.md`.

## Package E — Seed/data-state/harvest (Run #168 baseline)

- **Tek güvenli düzeltme = harvest window (spec-only):** `04-folio-mass.spec.js` C4
  (void-charge) + C5 (void-payment) eskiden split/refund ile aynı folios[0..4]'ü
  örnekliyordu → void hedefleri tüketilmiş → vacuous `allEmpty`/`allNoPay`. Fix:
  `voidSampleWindow(src)` = `slice(10,15)` (yıkıcı aralık 0..9'un ötesi ama create
  aralığı içi), pool küçükse `slice(0,5)` fallback. Status ladder aynen korundu → yeni
  FAIL sınıfı yok, assertion gevşetme yok.
- **CONFIRM-BY-DESIGN (6):** finance_folio `no_created_payment_to_void`; notification
  activity feed empty (zaten P2, FAIL etmez); VCC no booking; full_24h scarcity;
  revenue_mgmt hurdle/queue IDOR; city ledger.
- **DO_NOT_TOUCH-pilot (2):** payment_pos_reconciliation OPEN-shift (kör-seed YASAK);
  accommodation_tax pilot declaration pool (pilot mutation yok).
- **Roadmap (1+1):** POS recipe/BOM seed (out-of-scope, kör-seed riski→ertelendi) +
  public_token rotation endpoint (env-only `ROOM_QR_SECRET`). `node --check` PASS.
- **Drill:** `docs/drill_reports/20260530_review_skip_package_e_{inventory,candidate}.md`.

## Package F — Frontend/UI selector & render coverage (Run #168 baseline)

- **Kritik kapsam bulgusu:** tüm `frontend/e2e-stress/specs/` içinde gerçek browser
  render (`browser.newContext`+`page.goto`+`.locator`+TTI) yapan TEK spec =
  `08-housekeeping-mass.spec.js`; diğer "UI" REVIEW/SKIP'ler API/HTTP probe (Paket D/E),
  selector DEĞİL.
- **Tek güvenli düzeltme = selector+route drift (spec-only):** FE render TTI testi
  `/housekeeping` (= `HousekeepingDashboard`, oda grid'i yok) hedefliyordu + selector
  whitelist grid'in gerçek testid'leriyle eşleşmiyordu → kalıcı vacuous `noRows→REVIEW`.
  Gerçek grid: `/housekeeping-status` → `HousekeepingStatusPage` → `HousekeepingRoomGrid`;
  oda `room-card-<n>`, durum butonu `status-btn-<n>-<key>`. Fix (3 spec edit): route
  güncellendi; `[data-testid^="room-card-"]` + `[data-testid^="status-btn-"]` prefix
  selector'ları eklendi (legacy fallback korundu). Status ladder aynen korundu.
- **Şeffaf CI-deferred risk:** fix önceden-vacuous FAIL gate'i aktifleştirir; grid
  virtualization'sız → seedli full-suite'te ya REVIEW→PASS (güçlendirme) ya da gerçek
  500-oda perf breach → P2+FAIL (intended detection, test-logic regresyonu DEĞİL).
  Strict-GREEN çözümü ürün kararı (virtualization) / perf-gate re-baseline'dır, testi
  gevşetmek değil.
- **CONFIRM-BY-DESIGN (4):** notification/messaging + frontdesk + admin/settings +
  marketplace/POS — DOM-render stress spec'i yok; yeni UI-render coverage = ROADMAP.
- **Drill:** `docs/drill_reports/20260530_review_skip_package_f_{inventory,candidate}.md`.

---

## Ne kod / spec / docs-only idi

- **Backend kod değişen paketler:** A+B (Exely test-auth gate), C (e-Fatura tax-id parite).
- **Spec-only düzeltme:** D (cross-tenant pentest path-drift), E (folio-mass harvest
  window), F (housekeeping route+selector drift).
- **Docs-only (bu tur):** baseline chain + paket özeti + GOTCHAS reorganizasyonu.

## Kasıtlı olarak bırakılanlar

- **ROADMAP:** QR public_token rotation HTTP endpoint; POS recipe/BOM seed; yeni browser
  UI-render coverage (messaging/frontdesk/admin/POS); revenue global dry_run kill-switch;
  B2B per-subrouter scope; corporate-contract approval state machine; e-Fatura
  `customer_type` zorunlu.
- **CONFIRM-BY-DESIGN:** super_admin fail-closed 404 yüzeyleri (2xx=auth-weakening YASAK);
  KVKK anonymize-only; NPS 409 dedup; EntitlementMiddleware 403; QR HMAC-gated/PII-masked.
- **DO_NOT_TOUCH-pilot:** payment_pos_reconciliation OPEN-shift; accommodation_tax pilot
  declaration pool.

## Hatırlatma

Tüm paketler tamamlandıktan sonra **final full stress henüz yeniden koşturulmadı**.
Baseline pointer #168'de sabittir ve yalnız operatör dispatch'i + GREEN doğrulama
sonrası güncellenmelidir.
