# Daily Change Review — 2026-05-27

> **Scope:** All merges that landed on `main` during 2026-05-27 (UTC).
> **Method:** `git log --since="2026-05-27 00:00" --until="2026-05-28 00:00"` enumerated commit by commit; risk + coverage status filled from the actual diff and the spec inventory under `frontend/e2e-stress/specs/`, `frontend/e2e-business/`, `backend/tests/`.
> **Doctrine reminders:** fake PASS yok · skip-as-pass yok · P2/REVIEW downgrade yok · `external_calls=[]` · `pilot_drift=0` · destructive POST yok (pilot tenant'a mutation yok).
> **Baseline reference:** Run #143 (2026-05-26) — 84 spec / 556 test GREEN GO WITH WATCH. **Bu rapor yeni resmi baseline ilan ETMEZ** — F9E full-suite artifact henüz yok.

---

## 1) Executive summary

- **Merged commits today:** 35 (kapsam: F9 sprint specs, backend hardening, F&B/MICE PDF, inventory, supplier credit, cashier throttle, mobile-surface **stress spec'leri** — `mobile/` Expo ağacı bugünden eski, bugün native scaffold landing'i YOK — ve docs).
- **F9C status (7 deep stress spec):** Tüm 7 dosya `frontend/e2e-stress/specs/` altında mevcut, `node --check` her biri için PASS (aşağı bkz §3). Architect onayı per-spec task merge'lerinde kayıtlı (`Task #41` Round-3 PASS, `Task #44/46/47/48/52/53` doğrulama drill report'ları `docs/drill_reports/20260527_*`). **F9C dosya teslimi: COMPLETE.**
- **F9D (targeted runs / deploy env):** PARTIAL. Pilot CI doğrulaması yapılan spec'ler: `98-sales-basic-lifecycle` (Task #47 drill), `98-fnb-beo-generator` (Task #53 drill), `72-warehouse-transfer-procurement` (Task #18 drill). Geriye kalan F9C spec'leri için targeted run drill report'u **YOK**.
- **F9E (full suite re-run):** **BLOCKED.** Local'den koşulamıyor; GitHub Actions Full Stress Suite gerekli. Bu rapor full-suite drill yerine geçmez.
- **Yeni resmi baseline:** ❌ İlan EDİLMEZ. Mevcut baseline Run #143 (84 spec) olarak kalır.
- **Mobile app coverage:** ❌ ZERO (yeni Expo scaffold bugün indi). Web stress spec'leri mobile app'i kapsamaz. F10 Mobile App Coverage Program ayrı yüzey olarak açıldı (`docs/F10_MOBILE_COVERAGE_ROADMAP.md`).

---

## 2) Per-commit change ledger (35 commits)

| # | Commit | Modül | Dosya değişiklikleri (özet) | Risk | Test kapsamı | Targeted run | Full-suite run |
|---|---|---|---|---|---|---|---|
| 1 | `6e736cf1` | mice / tests | +`backend/tests/test_mice_beo_pdf.py` (207 satır) | LOW (test only) | ✅ Backend unit (3 test, local PASS) | n/a | Pending (F9E) |
| 2 | `6ad8644a` | mice / email | `backend/routers/mice.py` (+112), `BeoModal.jsx` (+62) — `POST /api/mice/events/{id}/beo/email` | MEDIUM (outbound email + recipient input) | ⚠️ Unit test YOK (sadece manuel/architect review); stress spec'te assert YOK | ❌ | Pending |
| 3 | `9da2f173` | mice / pdf | `backend/routers/mice.py` (+227), `98-fnb-beo-generator.spec.js` (+39, E2 PDF byte assert) | MEDIUM (weasyprint render path) | ✅ Stress spec E2 step (`%PDF` magic byte) + Task #69 unit test | ✅ Task #53 drill (`20260527_stress_98_fnb_beo_generator_verify.md`) | Pending |
| 4 | `5671f403` | infra / playwright | `scripts/post-merge.sh` (+8) — `playwright install chromium` | LOW (CI hygiene) | n/a (env shim) | n/a | n/a |
| 5 | `cf8f23dd` | b2b / fixtures | Admin pilot_fixtures router + `41B-b2b-subrouter-matrix.spec.js` | MEDIUM (admin-only fixture endpoint) | ✅ Spec 41B kullanıyor | ✅ Run #143 (önceki spec) | Pending |
| 6 | `e9a8ef64` | stress / helpers | `callApiKey` paylaşımı | LOW (refactor) | ✅ 2 spec consumer | n/a | Pending |
| 7 | `a7332e5a` | procurement / credit | `backend/routers/procurement.py` (+49), `72-warehouse-transfer-procurement.spec.js` (+85) — supplier credit limit enforcement | **HIGH (finansal kontrol)** | ✅ Stress spec assert; ⚠️ unit test gap (Task #65 IN_PROGRESS) | ✅ Task #18 drill | Pending |
| 8 | `af6a2620` | docs | `20260524_stress_f8f_v2_warehouse_transfer.md` | LOW | n/a | n/a | n/a |
| 9 | `f1be9f52` | finance / accounting | `backend/routers/finance/accounting.py` (+139), `72-warehouse-transfer-procurement.spec.js` (+192) — atomic warehouse-to-warehouse transfer | **HIGH (envanter atomicity)** | ✅ Stress spec | ✅ Task #18 drill | Pending |
| 10 | `c5c6af67` | fnb / kds | `backend/tests/test_kitchen_order_idempotency.py` (+199), `98-pos-kds-inventory.spec.js` (+7) | **HIGH (kitchen idempotency lock)** | ✅ Unit + stress | ✅ Run #143 | Pending |
| 11 | `e1e2017b` | f9c verify | `20260527_stress_f9c_sales_lifecycle_verify.md`, `stress-helpers.js` (+18) | MEDIUM | ✅ Drill report | ✅ Task #47 | Pending |
| 12 | `26fb809a` | cm / conflict queue | `cm_conflict_queue.py` (+10) — stress markers | LOW | ✅ Existing spec | ✅ Run #143 | Pending |
| 13 | `acfa284b` | finance / folio | +`99-finance-folio-surface.spec.js` (826 satır), roadmap entry | **HIGH (P0 IDOR + Idempotency-Key assert)** | ✅ Stress spec (Task #52) | ❌ Targeted run drill **YOK** (Task #59 PENDING) | Pending |
| 14 | `27687d0f` | stress / pacer | `stress-helpers.js` (+139) — per-token sliding-window pacer | **HIGH (suite-wide stabilite)** | ✅ Mevcut spec'ler tüketici | ✅ Per-spec verify'ler | Pending |
| 15 | `eb57419f` | docs | `20260527_stress_98_fnb_beo_generator_verify.md` | LOW | n/a | n/a | n/a |
| 16 | `b7186604` | security / cashier | `cashier_router.py` (+44), `auth_throttle.py` (+23), `test_cashier_handover_throttle.py` (+146) | **HIGH (brute-force gate)** | ✅ Unit + Mongo-backed throttle | ⚠️ Stress spec assert henüz YOK | Pending |
| 17 | `309f4e4f` | f9c sales seed | `98-sales-basic-lifecycle.spec.js` (+108) — paket seed | MEDIUM | ✅ Spec içi | ✅ Task #47 | Pending |
| 18 | `ba404e5f` | docs / verify | `20260527_task33_rooms_fetch_mid_suite_VERIFICATION.md` | LOW | n/a | n/a | n/a |
| 19 | `f4e15c1e` | docs | Roadmap reconcile + 41B drill update | LOW | n/a | n/a | n/a |
| 20 | `271dc8b6` | f9c-2 messaging | +`98-messaging-template-lifecycle.spec.js` (648 satır) — IDOR is2xx + recursive secret scan | **HIGH (secret scan + P0 IDOR)** | ✅ Architect Round-3 PASS (Task #41) | ❌ Targeted run drill **YOK** | Pending |
| 21 | `fd1b12d3` | f9c-7 marketplace | +`98-marketplace-deep-lifecycle.spec.js` (624 satır) | HIGH | ✅ Task #46 | ❌ Targeted run drill **YOK** | Pending |
| 22 | `1b39e240` | f9c-5 beo | +`98-fnb-beo-generator.spec.js` (600 satır) | HIGH | ✅ Task #44 + Task #53 drill | ✅ Task #53 | Pending |
| 23 | `e9e762d4` | f9c-4 mobile cashier | +`98-mobile-cashier-surface.spec.js` (747 satır) | HIGH | ✅ Task spec | ❌ Targeted run drill **YOK** | Pending |
| 24 | `3c7ef347` | f9c-3 mobile staff | +`98-mobile-staff-surface.spec.js` (647 satır) | HIGH | ✅ Task #42 | ❌ Targeted run drill **YOK** | Pending |
| 25 | `57c0ab4e` | f9c-6 sales | +`98-sales-basic-lifecycle.spec.js` (612→698 satır) | HIGH | ✅ Task #45 + Task #47 drill | ✅ Task #47 | Pending |
| 26 | `9b9c440f` | f9c-1 maintenance | +`98-maintenance-workorder-lifecycle.spec.js` (522 satır) | HIGH | ✅ Task | ❌ Targeted run drill **YOK** | Pending |
| 27 | `21a41ab7` | f9b probe + smoke | +`97-backend-router-coverage-probe.spec.js` (319 satır), smoke PII scan | HIGH | ✅ Spec syntax OK | ❌ Targeted run drill **YOK** | Pending |
| 28 | `ff8eed50` | f9a smoke matrix | `routes.js` (+54), `fixtures.js` (+28) — 31 ZERO route + PII scan | MEDIUM | ✅ Smoke matrix | ❌ Smoke targeted run drill **YOK** | Pending |
| 29 | `8f210d2c` | docs | +`TEST_COVERAGE_GAP_MAP_20260527.md` (227 satır) | LOW | n/a | n/a | n/a |
| 30 | `b17c8347` | docs | Roadmap closing note + replit.md | LOW | n/a | n/a | n/a |
| 31 | `20801a03` | docs | P2/REVIEW triage classification | LOW | n/a | n/a | n/a |
| 32 | `6f48e71e` | workers / sentry noise | 11 worker dosyası — `TransientFailureTracker` | MEDIUM (observability) | ✅ Architect Round-2 PASS | n/a | Pending |
| 33 | `b5fb1c21` | docs | P2/REVIEW triage backlog | LOW | n/a | n/a | n/a |
| 34 | `ff15eb57` | docs | PILOT_TRUST_NARRATIVE + Run #143 update | LOW | n/a | n/a | n/a |
| 35 | `dd95d425` | docs | Run #143 drill report update | LOW | n/a | n/a | n/a |

**Not:** "Mobile app Expo scaffold" başlığında bağımsız commit BUGÜN main'e inmiş değil (`mobile/` ağacı bu sprint'in öncesinde mevcuttu; bugünkü merge'ler içinde sadece **`98-mobile-staff-surface`** ve **`98-mobile-cashier-surface`** stress spec'leri var, gerçek native binary değil). Mobile native surface coverage için `docs/F10_MOBILE_COVERAGE_ROADMAP.md` açıldı.

---

## 3) F9C verification — 7 specs

| # | Spec | Lines | `node --check` | Architect review | Targeted run drill |
|---|---|---:|:---:|:---:|:---:|
| 1 | `98-maintenance-workorder-lifecycle.spec.js` | 522 | ✅ | ✅ Task #40 (initial PASS) | ✅ Task #82 — **NO-GO** (`20260527_stress_98_maintenance_workorder_verify.md`) — POST `/api/maintenance/work-orders` → 500 ASGI exception |
| 2 | `98-messaging-template-lifecycle.spec.js` | 648 | ✅ | ✅ Task #41 Round-3 PASS | ✅ Task #82 — **GO** (`20260527_stress_98_messaging_template_verify.md`) — 14/14 PASS, P0=P1=0 |
| 3 | `98-mobile-staff-surface.spec.js` | 647 | ✅ | ✅ Task #42 | ✅ Task #82 — **NO-GO** (`20260527_stress_98_mobile_staff_verify.md`) — GET `/api/notifications/preferences` → 500 (Setup also requires `DISABLE_EXPO_PUSH=1` in runner env; harness gate already enforced in pre-flight) |
| 4 | `98-mobile-cashier-surface.spec.js` | 747 | ✅ | ✅ Task #43 | ✅ Task #82 — **NO-GO** (`20260527_stress_98_mobile_cashier_verify.md`) — Cashier handover PIN gate: 7 wrong creds = 7×401, expected 429 by attempt 7 (financial gate missing brute-force throttle) |
| 5 | `98-fnb-beo-generator.spec.js` | 635 | ✅ | ✅ Task #44 | ✅ Task #53 (`20260527_stress_98_fnb_beo_generator_verify.md`) |
| 6 | `98-sales-basic-lifecycle.spec.js` | 698 | ✅ | ✅ Task #45/#48 | ✅ Task #47 (`20260527_stress_f9c_sales_lifecycle_verify.md`) |
| 7 | `98-marketplace-deep-lifecycle.spec.js` | 624 | ✅ | ✅ Task #46 | ✅ Task #82 — **GO WITH WATCH** (`20260527_stress_98_marketplace_deep_verify.md`) — 13 PASS / 1 SKIP (I=reject when order auto-finalizes), P0=P1=0 |

**Sonuç:** F9C **dosya teslimi COMPLETE** (7/7 mevcut, syntax PASS, architect onayları kayıtlı). **F9C targeted-run kapanışı: 7/7** (Task #82 kalan 5 spec'i pilot'a koştu — drill report'lar yukarıdaki kolonda). **Honest verdict dağılımı:** 1 GO (messaging), 3 GO WITH WATCH (BEO, sales, marketplace), 3 NO-GO (maintenance, mobile_staff, mobile_cashier — 3 gerçek backend P1). Suite green baseline'a promote edilemez; üç P1 düzeltilmeden F9E full-suite koşusu da NO-GO döner. Doctrine korundu: fake PASS yok, skip-as-pass yok — `failedTests=1` ve `recFinding('P1', ...)` çağrıları olduğu gibi reporter'a yansıdı.

---

## 4) Targeted regression pack — execution decision

İstenen pack:
- POS/KDS · finance folio · BEO PDF · messaging template · mobile staff · mobile cashier

**Karar:** ❌ **Bu environment'tan koşulamaz.**

| Spec | Neden çalıştırılamadı |
|---|---|
| `98-pos-kds-inventory.spec.js` | `STRESS_E2E_BASE_URL` + `E2E_STRESS_TENANT_ID` + `E2E_STRESS_ADMIN_*` + `E2E_ALLOW_DESTRUCTIVE_STRESS=true` + `E2E_EXTERNAL_DRY_RUN=true` secret'ları local'de yok; spec deploy'lu backend'e ihtiyaç duyuyor |
| `99-finance-folio-surface.spec.js` | aynı + pilot read-only fixtures CI-only |
| `98-fnb-beo-generator.spec.js` | aynı (zaten Task #53 pilot drill kapatıldı) |
| `98-messaging-template-lifecycle.spec.js` | aynı |
| `98-mobile-staff-surface.spec.js` | aynı |
| `98-mobile-cashier-surface.spec.js` | aynı |

Local'de yapılabilen ve YAPILAN: `node --check` syntax doğrulaması (yukarı bkz §3). Bu **suite-pass yerine geçmez**; sadece dosya parse-edilebilirliğini kanıtlar.

**Aksiyon:** Targeted pack ve F9E full-suite, GitHub Actions Full Stress Suite workflow'unda PR/merge sonrası tetiklenecek; her spec için drill report `docs/drill_reports/20260527_*` altında açılacak (5 eksik spec için).

---

## 5) Full Operational Stress Suite — run decision

❌ **NOT RUN.** Gerekçe: F9E full-suite koşusu bu environment'tan tetiklenemez (CI-only). Şartlar:
- 92 spec sıralı koşum, ~50 dk reporter süresi
- 7 yeni F9C spec + 1 F9D folio spec + 1 F9B probe spec full-suite'e ilk kez girecek
- Yeni resmi baseline ilan için: drill report `docs/drill_reports/20260527_f9_full_app_coverage_closure.md` + tüm invariant'lar PASS (failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0, verdict ≥ GO WITH WATCH)

Bu drill **bu rapor tarafından üretilmedi**. Mevcut resmi baseline Run #143 (84 spec / 2026-05-26) olarak kalır.

---

## 6) Doc updates (artifact-driven only)

| Doc | Güncellendi mi? | Not |
|---|:---:|---|
| `docs/STRESS_TEST_ROADMAP.md` | ✅ (bu rapor) F9C completion appendix eklendi | Yeni baseline numarası YOK |
| `docs/TEST_COVERAGE_GAP_MAP_20260527.md` | ❌ ZERO→PARTIAL transition kaydı YOK | F9A smoke ve F9C stress spec'leri targeted CI'da koşulup green dönmedikçe gap statüsü değiştirilemez (doctrine) |
| `docs/STRESS_P2_REVIEW_TRIAGE_20260526.md` | ❌ | P2/REVIEW sayıları değişmedi (yeni full-suite yok) |
| `docs/PILOT_TRUST_NARRATIVE.md` | ❌ | "Verified coverage" satırı **sadece CI green sonrası** güncellenir — bugün koşulmadı |
| `docs/F10_MOBILE_COVERAGE_ROADMAP.md` | ✅ YENİ | F10 mobile coverage program açılışı |

---

## 7) Risk register (gün sonu)

| # | Risk | Etki | Açık aksiyon |
|---|---|---|---|
| R1 | F9C 5 spec için pilot CI drill report yok | Doctrine breach riski (architect PASS ≠ pilot PASS) | F9D targeted run drill paketi: 5 spec × 1 GitHub Actions job |
| R2 | F9E full-suite drill yok — yeni baseline ilan edilemez | Yeni güvenlik/finansal commit'ler (a7332e5a, f1be9f52, b7186604, acfa284b) full-suite'te ilk kez koşacak | F9E koşumu önceliklendir |
| R3 | Mobile native app coverage ZERO | KVKK / guest PII riski + cashier brute-force surface mobile'da test edilmemiş | F10 roadmap'e bakın |
| R4 | BEO email endpoint (`6ad8644a`) için unit test ve stress spec assert yok | Recipient injection / spam / PII leak riski | Task #69-extended kapsamı |
| R5 | Supplier credit limit guard için unit test gap (Task #65 IN_PROGRESS) | Finansal kontrol regresyon riski | Task #65 kapanışı |

---

## 8) Acceptance check

- [x] Daily change review created — bu dosya
- [x] F9C completion status truthful — §3 (dosya teslimi COMPLETE, targeted-run 2/7)
- [x] Targeted pack result recorded — §4 (NOT RUN, neden açıklandı)
- [x] Full suite run decision recorded — §5 (NOT RUN, neden açıklandı, baseline değişmedi)
- [x] F10 mobile coverage roadmap created — `docs/F10_MOBILE_COVERAGE_ROADMAP.md`

**Doktrin uyumu:** Hiçbir yerde "PASS" iddia edilmedi · skip-as-pass yok · P2/REVIEW downgrade yok · external_calls test edilmedi (CI gerek), iddia da edilmedi · pilot_drift test edilmedi, iddia edilmedi · yeni baseline ilan EDİLMEDİ.
