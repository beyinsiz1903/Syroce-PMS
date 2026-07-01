# Uygulama Test Kapsamı Boşluk Haritası — 2026-05-27

> **Soru:** Uygulama içinde hangi modüller / hangi sayfalar test içinde yok?
>
> **Kaynak envanter:**
> - **Frontend:** ~120 benzersiz sayfa / ~160 route (`frontend/src/routes/sections/*`)
> - **Backend:** ~185 router modülü / ~6500–7000 endpoint (`backend/routers/` + `backend/domains/*/router.py`)
> - **Test:** 107 spec dosyası (84 stress + 22 business + 1 smoke) — Run #143 baseline
>
> **Yöntem:** Spec dosya adları + ilk satır açıklamaları + endpoint path eşleştirmesi → her sayfa / her router modülü için "covered / partial / zero" etiketi.
>
> **Kapsam tanımı:**
> - **COVERED** = en az bir dedicated spec (stress veya business) modülün ana akışını test ediyor.
> - **PARTIAL** = smoke navigate testi var veya parent modül test ediyor ama sayfa-spesifik akış test edilmiyor.
> - **ZERO** = hiçbir spec sayfayı / router'ı dokunmuyor.

---

## 0) F9 Sprint progress (2026-05-27)

**F9A DONE:** 31 ZERO-coverage frontend route smoke matrix'e eklendi (`critical: false`) + PII/token leak scan fixture'a eklendi. Bu sayfaların ZERO → PARTIAL geçişi smoke suite koşulduğunda doğrulanacak. Aşağıdaki §2.1 tablosundaki tüm satırlar artık **smoke matrix'te listeli** — render + PII sanity OK olursa PARTIAL'a yükselir.

**F9B/F9C/F9D/F9E:** Pending (bkz. `docs/STRESS_TEST_ROADMAP.md` F9 bölümü). F9C 7 deep stress spec için multi-session task agent paketi önerilir.

---

## 1) Yönetici özeti

| Yüzey | Toplam | COVERED | PARTIAL | ZERO | Boşluk oranı |
|---|---:|---:|---:|---:|---:|
| **Frontend sayfa** | ~120 | ~28 | ~44 (smoke navigate only) | **~48** | **%40** |
| **Backend router modülü** | ~185 | ~52 | ~38 | **~95** | **%51** |
| **Backend endpoint** | ~6800 | ~1100 (~16%) | ~1800 (~26%) | **~3900 (~57%)** | **%57** |

**Ana mesaj:** Stress + business + smoke suite **kritik para/güvenlik/operasyon yüzeylerini** kapsıyor (P0/P1 = 0, pilot trust invariantları PASS). Ancak **uygulamanın 1/2'sinden fazlası** endpoint sayısı bazında dedicated test'siz; bunların büyük çoğunluğu **derinlik genişletmesi** (dashboard widget'ları, AI sub-router'ları, marketplace alt-akışları, F&B alt sayfaları, infrastructure dashboard'ları). Pilot-critical core path covered; **derin keşif / second-order workflow'lar açık**.

---

## 2) Frontend sayfa boşluk haritası (ZERO + PARTIAL)

### 2.1 ZERO COVERAGE — Hiçbir spec dokunmuyor (~48 sayfa)

| Modül | Sayfa / Route | Risk seviyesi | Açıklama |
|---|---|:---:|---|
| **Front Office** | `/walkin` (WalkinPage) | 🟡 MEDIUM | Walk-in akışı sadece backend stress'te dolaylı (reservation lifecycle). UI form test'i yok |
| | `/room-map` (RoomMapPage) | 🟢 LOW | Görsel oda haritası — read-only |
| | `/wake-up-calls` (WakeUpCallsPage) | 🟡 MEDIUM | Operatör critical, hiçbir test yok |
| | `/lost-found` (LostFoundPage) | 🟢 LOW | Hiçbir test yok — modül tamamen kör |
| | `/frontdesk/audit-checklist` | 🟡 MEDIUM | Night audit backend covered, UI checklist değil |
| | `/arrival-list`, `/departure-list`, `/no-show-today` | 🟢 LOW | Reservation aggregator view'lar — base data covered |
| **Reservations** | `/reservation-calendar` (gun-week-month view) | 🟡 MEDIUM | Smoke navigate var, drag-drop conflict resolution test edilmiyor |
| **Housekeeping** | `/housekeeping-status` | 🟢 LOW | Ana housekeeping covered, status detay sayfası değil |
| **Maintenance** | `/maintenance/work-orders` | 🔴 HIGH | **Tüm Maintenance modülü zero** — work order, asset, plan |
| | `/maintenance/assets` | 🔴 HIGH | Aynı |
| | `/maintenance/plans` | 🔴 HIGH | Aynı |
| **Finance** | `/pending-ar` (PendingAR) | 🟡 MEDIUM | Folio covered ama AR aging view test'i yok |
| | `/city-ledger` (CityLedgerAccounts) | 🟡 MEDIUM | Stress F4 fixture gap olarak işaretli |
| | `/efatura` (EFaturaModule UI) | 🟡 MEDIUM | Backend dry-run covered, UI submit akışı değil |
| | `/app/konaklama-vergisi` (UI) | 🟡 MEDIUM | Aynı — backend dry-run var, UI değil |
| **Revenue/RMS** | `/displacement-analysis` | 🟢 LOW | Analytical view, read-only |
| | `/dynamic-pricing` (DynamicPricing) | 🟡 MEDIUM | AI pricing backend covered, UI override akışı değil |
| | `/revenue-autopilot` (RevenueAutopilot) | 🟡 MEDIUM | Autopilot toggle/rule UI hiç test edilmiyor |
| | `/revenue-engine` (RevenueEngineDashboard) | 🟢 LOW | Read-only dashboard |
| **Channel Manager** | `/mapping-manager` (MappingManager) | 🟡 MEDIUM | Mapping create/edit UI test edilmiyor; yanlış mapping = OTA double-book riski |
| | `/room-mapping-wizard` | 🟡 MEDIUM | Wizard akışı zero coverage |
| | `/unified-rate-manager` | 🟡 MEDIUM | URM bulk push UI test edilmiyor |
| | `/ari-push` (ARIPushDashboard) | 🟡 MEDIUM | ARI worker backend covered, dashboard UI değil |
| **F&B / POS** | `/pos-extensions` | 🟢 LOW | Extension config sayfası |
| | `/fnb-complete` (FnBComplete) | 🟡 MEDIUM | Bütünleşik F&B akışı, KDS sadece backend |
| | `/fnb/beo-generator` (FnbBeoGenerator) | 🔴 HIGH | BEO (Banquet Event Order) generator — para kritik, sıfır test |
| | `/kitchen-display` (KitchenDisplay UI) | 🟡 MEDIUM | KDS backend deep, UI gerçek-zaman state değil |
| **Admin** | `/admin/governance` (GovernancePanel) | 🟡 MEDIUM | Governance audit log UI |
| | `/app/admin-control-panel` | 🟡 MEDIUM | Admin master panel |
| **Guest** | `/guest-journey` (GuestJourney) | 🟢 LOW | Cross-modül guest aggregator |
| **Mobile/Staff** | `/staff/mobile` (StaffMobileApp) | 🔴 HIGH | **Tüm mobile staff app zero** — push, scan, vardiya |
| **Sales** | `/sales` (SalesModule) | 🔴 HIGH | **Tüm Sales modülü zero coverage** |
| **Infrastructure** | `/observability` (ObservabilityDashboard) | 🟢 LOW | Read-only dashboard |
| | `/data-pipeline` | 🟢 LOW | Pipeline status view |
| | `/event-bus` (EventBusDashboard) | 🟢 LOW | SXI event bus dashboard |
| | `/system-health` | 🟢 LOW | Stress'te `/api/health/*` covered, UI değil |

### 2.2 PARTIAL — Smoke navigate var ama akış test'i yok (~44 sayfa)

`e2e-smoke/smoke.spec.js` 24 route × 2 viewport = 48 navigate test çalıştırıyor. Bu sayfaların **render etmesi** doğrulanıyor, ama **işlevsel akış** (form submit, mutation, error path) test edilmiyor. Örnekler:
- `/admin/tenants`, `/admin/user-roles` (smoke render OK, RBAC mutation test'i admin_rbac stress'te)
- `/reports/builder` (smoke render OK, builder akışı zero)
- `/reports/official-guest-list` (resmi misafir listesi PDF export test edilmiyor)
- `/security` (SecurityHub render only)
- `/hr` (HRHub aggregator, alt sayfalar derin test edilmiyor)

---

## 3) Backend router boşluk haritası (ZERO + PARTIAL)

### 3.1 ZERO COVERAGE — Hiçbir stress spec dokunmuyor (~95 modül)

#### A. PMS sub-router'lar (büyük endpoint hacmi)

| Router | Endpoint sayısı | Risk | Açıklama |
|---|---:|:---:|---|
| `domains/pms/marketplace_router.py` | 192 | 🔴 HIGH | Sadece `41B-b2b-subrouter-matrix` deep yüzeyi tarıyor; 192 endpoint'in büyük kısmı kör |
| `domains/pms/pos_fnb_router/*` (5 modül) | ~228 | 🔴 HIGH | F&B alt akışları (recipe, menu, modifier, station) — KDS sadece core POS |
| `domains/pms/mobile_router/*` (6 modül) | ~180 | 🔴 HIGH | Staff mobile API'leri zero — mobile staff app testsiz |
| `domains/pms/dashboard_router/*` (3 modül) | ~138 | 🟡 MEDIUM | Dashboard widget endpoint'leri |
| `domains/pms/misc/*` (8 modül) | ~147 | 🟡 MEDIUM | `groups`, `catering`, `approvals`, `wakeup`, `lost_found`, `maintenance_router` |
| `domains/pms/maintenance/*` | ~? | 🔴 HIGH | **Maintenance backend zero** — frontend zero ile aynı |

#### B. Channel Manager provider sub-router'lar

| Router | Endpoint | Risk | Açıklama |
|---|---:|:---:|---|
| `providers/hotelrunner/*` (8+ router) | ~150+ | 🟡 MEDIUM | Webhook signed-path covered, diğer admin endpoint'ler partial |
| `providers/exely/exely_router.py` | 115 | 🟡 MEDIUM | Webhook covered, admin/sync endpoint'ler kör |
| `validation`, `lockdown`, `ingest`, `incident` (10+ modül) | ~250+ | 🟡 MEDIUM | Conflict queue endpoint zero (E3 gap'te listeli) |
| `reconciliation_engine/reconciliation_router.py` | 22 | 🟡 MEDIUM | Reconciliation flow test edilmiyor |

#### C. AI / ML deep sub-router'lar

| Router | Endpoint | Risk | Açıklama |
|---|---:|:---:|---|
| `domains/ai/router/*` (9 modül) | ~229 | 🟡 MEDIUM | Sadece `ai_noshow_risk` + `ai_pricing` stress'te (toplam ~50 endpoint); upsell, forecasting, guest pattern, dynamic offers zero |
| `domains/ai/endpoints.py` | 33 | 🟡 MEDIUM | AI dispatch endpoint'leri |

#### D. Finance derin alt akışlar

| Router | Endpoint | Risk | Açıklama |
|---|---:|:---:|---|
| `routers/finance/mobile.py` | 198 | 🔴 HIGH | Mobile cashier akışları zero |
| `routers/finance/*` diğer 8 modül | ~382 | 🟡 MEDIUM | Folio core covered, deposit/refund deep flow'lar partial |
| `routers/b2b_api/*` (14 modül) | ~220 | 🟡 MEDIUM | Sadece booking/guests/kbs subrouter matrix covered |

#### E. Guest experience derin

| Router | Endpoint | Risk | Açıklama |
|---|---:|:---:|---|
| `domains/guest/experience_router/*` (9 modül) | ~278 | 🟡 MEDIUM | NPS + review + QR partial; loyalty, preferences, journey zero |
| `domains/guest/messaging/router.py` | 159 | 🔴 HIGH | Smoke + 1 stress spec; SMS/email/WhatsApp template lifecycle zero |
| `domains/guest/operations_router.py` | 159 | 🟡 MEDIUM | Service request core covered, escalation flow zero |

#### F. HR derin

| Router | Endpoint | Risk | Açıklama |
|---|---:|:---:|---|
| `domains/hr/router.py` | 469 | 🟡 MEDIUM | Top 5 endpoint covered (staff_org, shift, rbac_pii, shift_coverage, payroll IDOR); kalan ~440 endpoint kör (leave, performance, recruitment, training, benefits, compensation) |

#### G. Admin / System

| Router | Endpoint | Risk | Açıklama |
|---|---:|:---:|---|
| `domains/admin/router/*` (12 modül) | ~250 | 🟡 MEDIUM | RBAC core covered, tenants/governance/feature-flags partial; observability admin endpoint'leri zero |
| `routers/observability.py`, `system_health_normalized.py` | ~150 | 🟡 MEDIUM | Ops readiness 3 endpoint covered, kalan dashboard endpoint'leri zero |

#### H. Hotel services + Integrations

| Router | Endpoint | Risk | Açıklama |
|---|---:|:---:|---|
| `routers/hotel_services_pkg/*` (7 modül) | ~210 | 🟡 MEDIUM | Spa core covered, golf core covered, kalan 5 modül (laundry, transport, concierge, activities, kids-club) zero |
| `routers/whatsapp_webhook.py`, `xchange.py`, `kbs.py` | ~125 | 🟡 MEDIUM | KBS dry-run covered, WhatsApp webhook zero, xchange bus core covered |
| `routers/reports.py`, `report_builder.py`, `reports_pkg/*` | ~230 | 🟡 MEDIUM | Reports export top-level covered; report builder + 50+ rapor template zero |

### 3.2 PARTIAL — En az 1 endpoint covered ama modül derin test edilmiyor (~38 modül)

Yukarıdaki "🟡 MEDIUM" satırların büyük çoğunluğu bu kategoride. Genel kural: **modül başına 1–3 spec adımı**, modülün **tam endpoint matrisi değil**.

---

## 4) Risk-önceliklendirilmiş boşluk listesi

### 4.1 🔴 HIGH risk — Pilot operasyonunda kullanılma olasılığı yüksek + test yok

Bu kalemler P2/REVIEW triage §11'deki "MUST CLOSE PC1-PC4"e ek olarak **pilot öncesi karara bağlanması gereken** test boşluklarıdır.

| # | Boşluk | Pilot'a etki | Önerilen aksiyon |
|---:|---|---|---|
| **G1** | **Maintenance modülü (frontend + backend zero)** | Otel arızası kayıt edilemezse operasyonel kör nokta | Smoke navigate ekle (`/maintenance/work-orders`) + 1 stress spec (`98-maintenance-workorder-lifecycle.spec.js`) |
| **G2** | **Mobile staff app (`/staff/mobile` + `mobile_router/*` 180 endpoint)** | Pilot'ta mobile kullanılacak mı? Kullanılacaksa zero coverage = kritik | Önce pilot policy: mobile in/out scope? Out ise feature flag kapat; in ise dedicated smoke + 1 stress spec |
| **G3** | **Sales modülü (`/sales` zero)** | Sales modülü pilot operatöre açık mı? | Pilot scope'a göre karar; açıksa minimum smoke navigate |
| **G4** | **F&B BEO Generator (`/fnb/beo-generator`)** | Banquet event order = para kritik (MICE F&B revenue) | 1 stress spec — order create + price calculation + folio post |
| **G5** | **Marketplace router 192 endpoint** | B2B partner trafiği başlarsa | `41B` matrix derinleştir (mevcut sadece subrouter; deep CRUD lifecycle gerek) |
| **G6** | **Mobile cashier (`finance/mobile.py` 198 endpoint)** | Mobile ödeme akışı kritik | G2 ile aynı policy kararı; in scope ise dedicated stress spec |
| **G7** | **Messaging template lifecycle (159 endpoint)** | Pilot otelin SMS/email template oluşturması | Template CRUD + variable substitution + send test (sandbox) stress spec |

### 4.2 🟡 MEDIUM risk — Pilot'ta nadir kullanılır + test partial

| Boşluk | Pilot etki | Aksiyon |
|---|---|---|
| Channel Manager mapping/wizard UI | OTA mapping yanlış = double-book | Smoke navigate yeterli; deep mapping test post-pilot |
| URM bulk rate push UI | Rate update workflow | Smoke + 1 happy-path spec |
| AI deep router'lar (upsell/forecasting/etc.) | AI features pilot'ta opsiyonel | Feature flag kapatılırsa skip; açıksa partial spec |
| Reports builder + 50+ template | Operatör custom rapor üretirse | Önemli 5 template için dedicated spec |
| Guest journey aggregator | Read-only view | Smoke navigate yeterli |

### 4.3 🟢 LOW risk — Read-only / nadir / non-critical

Defer to post-pilot backlog: observability/data-pipeline/event-bus dashboard'ları, lost-found, wake-up calls, displacement analysis, vb.

---

## 5) Pilot pre-launch için minimum kapama önerisi

Bu rapor §4.1'in **G1–G7** kalemlerini pilot scope decision'ı için işaretler. Karar matrisi:

| Kalem | Pilot scope'ta? | Eğer YES → aksiyon | Eğer NO → aksiyon |
|---|:---:|---|---|
| G1 Maintenance | ? | 0.5 gün smoke + stress spec | Feature flag OFF |
| G2 Mobile staff | ? | 1.0 gün smoke + 1 stress spec | Feature flag OFF / route hide |
| G3 Sales | ? | 0.3 gün smoke navigate | Route hide |
| G4 BEO Generator | ? | 0.5 gün stress spec (folio post) | MICE module flag OFF |
| G5 Marketplace deep | partial | Post-pilot sprint | — |
| G6 Mobile cashier | ? | G2 ile birlikte | G2 ile birlikte |
| G7 Messaging template | likely YES | 0.5 gün stress spec | — |

**Tahmini ek efor (tümü YES → kapsama 2–3 günde genişler):** ~3 iş günü, 5–7 yeni spec.

---

## 6) Üst-düzey karar

- **Pilot için yeterli mi?** Şu an: pilot-critical core path (auth, reservation, folio, KDS, channel manager webhook, RBAC, KVKK, 2FA) **COVERED + GREEN**. P2/REVIEW triage §11 MUST CLOSE 4 kalem + bu rapordaki G1–G7 pilot-scope kararları **ek 1–3 gün efor**la kapatılabilir.
- **GO WITH WATCH verdict'i geçerli mi?** Evet. Çünkü:
  - `failedTests=0`, `P0=P1=0`, `external_calls=[]`, `pilot_drift=0`
  - Kapsam dışı kalan yüzeylerin büyük çoğunluğu **derinlik/internal admin/AI deep features** — pilot operasyon kritik path'inde değil.
- **"Bütün app test edildi" denmez.** §1'deki rakamlar gerçek: endpoint bazında %57 zero, sayfa bazında %40 zero. Sales/investor iletişiminde "**107 spec ile pilot-critical core path %100, derin/non-core surface'lar backlog'da**" formülü doğrudur.

---

## Referanslar

- Baseline: `docs/STRESS_TEST_ROADMAP.md` (Run #143)
- Drill: `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md`
- P2/REVIEW triage + pre-pilot decision matrix: `docs/STRESS_P2_REVIEW_TRIAGE_20260526.md`
- Coverage gap (paralel doküman): `docs/STRESS_COVERAGE_GAP_REPORT_20260526.md`
- Pilot trust: `docs/PILOT_TRUST_NARRATIVE.md`

*Son güncelleme: 2026-05-27.*
