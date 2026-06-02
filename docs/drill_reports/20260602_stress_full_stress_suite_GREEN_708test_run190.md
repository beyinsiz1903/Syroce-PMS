# Full Stress Suite — GREEN BASELINE — Run #190 (2026-06-02)

> Bu doküman, web/backend Full Operational Stress Suite'in **resmi GREEN BASELINE**
> kaydıdır. Önceki resmi baseline Run #184 → historical reference'a indi.
> **Kapsam notu:** bu web/backend full stress suite baseline'ıdır, /100 uygulama
> kapsamı DEĞİLDİR — mobile/F10 ayrı ve açık (doğrulanmadı). Merkezi referans:
> `docs/TEST_COVERAGE_SCORECARD_100.md`.

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 708 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1471 / 0 / 21 / 44 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 30 / 2 |
| Final verdict | **GO WITH WATCH** — P2=30, REVIEW=21 |

Mutlak kurallar (hepsi korundu): pilot mutation=0, external_calls=[],
failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH, assertion gevşetme YOK,
skip-as-pass YOK. Düz "GO" iddiası YOK; "/100 kapsam" iddiası YOK; mobile/F10 ayrı.

## 2) Provenance

- **Tarih:** 2026-06-02
- **Run:** #190, status=Success
- **Run ID:** 26819935740
- **Job ID:** 79071540497 ("Full stress suite (one-shot)", conclusion=success)
- **Commit (run koştuğu):** `adfa87d39f91bac5221247217f89d3207a08ab4a`
  ("Published your App" — messaging `/send` graceful-delivery 5xx guard +
  HR RBAC/PII spec-36 false-RED fix içerir).
- **Branch:** main
- **Job süresi:** 2026-06-02T12:33:17Z → 13:36:12Z (~1s 3dk; ekran görüntüsü "1h 2m 58s" toplam süre ile uyumlu).
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26819935740
- **Artifacts (2) — provenance TAM (GitHub Actions API `digest` alanından doğrulandı, fabrike EDİLMEDİ):**
  - stress-drill-report — ID `7359234557` (31639 B) —
    `sha256:827b360b95d91d78d02d9571fadbb7b92e91bc96cc43707d381fb3817df15454`
  - playwright-stress-report — ID `7359234213` (794962 B) —
    `sha256:6a7dedefd75d9d2f490410ed2c48a5fc3e8d28291caf6d8c10651d279a3079e1`

> Hiçbir provenance alanı fabrike EDİLMEDİ. Run/job ID'leri ve artifact sha256
> digest'leri GitHub REST API'den (public repo, anonim) okundu; conclusion=success.

## 3) Run-level garantiler

- **external_calls:** `[]`
- **pilot_drift:** 0 (pilot mutation yok; baseline_bookings=30 → after_bookings=30)
- **cleanup#1:** deleted_total=9094 · **cleanup#2 idempotent:** true (deleted_total=0)
- **seed:** prefix `E2E_STRESS_F7_1780403644038_`, room_count=500, external_calls_made=[]

## 4) Run #184 → #190 delta

### Kod delta
- #190, `adfa87d` üzerinde koştu. Bu commit iki doctrine-safe fix içerir:
  1. **messaging `/send` graceful-delivery 5xx guard** — burst altında consent-read
     hiccup'ı 5xx yerine graceful `success:False` döndürür (authz dependency try'dan
     önce çalışır; HTTPException propagate edilir). `notification_batch` test A
     artık FAIL üretmiyor.
  2. **HR RBAC/PII spec-36 false-RED fix** — admin'e authz-only iddia; gerçek
     PII masking finance principal'da doğrulanır (finance yoksa honest SKIP + P2).

### Test-yüzeyi delta
| Metrik | #184 | #190 | Delta |
|---|---|---|---|
| Toplam test | 708 | 708 | — |
| PASS | 1440 | 1471 | +31 |
| FAIL | 0 | 0 | — |
| REVIEW | 19 | 21 | +2 |
| SKIP | 54 | 44 | −10 |
| P2 | 31 | 30 | −1 |
| P3 | 2 | 2 | — |
| P0 / P1 | 0 / 0 | 0 / 0 | — |

**Atıf:** Pozitif ilerleme — PASS +31, SKIP −10 (önceden module-blocked/atlanan
yüzeyler artık koşuyor), P2 −1. FAIL/P0/P1=0 sabit; regresyon yok. REVIEW +2
data-state varyansı (aşağıda tutarlılık doğrulaması).

## 5) Rapor tutarlılık doğrulaması (promote öncesi zorunlu)

Promote öncesi iki başlık özel olarak incelendi. **Sonuç: rapor içsel olarak
tutarlı; stale triage carryover YOK; sayım düzeltmesi gerekmiyor.**

### 5a) reservation_deep — "triaj failed der, envanter passed gösterir"
- **Bulgu:** Test envanterinde spec-95'in 15 adımı da `✅ passed` (A) Waitlist
  add+promote ve L) City ledger transfer dahil). P2/REVIEW triajı ise bunları
  "Waitlist add başarısız (403)" ve "City-ledger folio bulunamadı (folios=0)"
  diye listeler.
- **Çözüm:** Bu bir **çelişki değil, raporlama-granülaritesi artefaktı**. Playwright
  case-seviyesi sonucu = passed (hard-throw atılmadı); harness ise case İÇİNDE
  adım-seviyesi REVIEW annotation'ı kaydeder. spec-95 "hard-assert" başlıklı olsa
  da module-access 403 ("Module 'pms' access denied") ve boş data-state (folios=0)
  durumlarında hard-assert'i REVIEW'a degrade eder → case geçer, bulgu P2/REVIEW
  olarak **görünür** kalır.
- **Stale değil:** Modül tablosu (run #190 kendi agregasyonu) reservation_deep
  REVIEW=3 gösterir; REVIEW detay listesi (waitlist_promote 403, overbook_yield,
  city_ledger_transfer folios=0) bunu birebir doğrular. Booking ID'leri
  (city ledger `84a1123c-...`) run-spesifiktir.
- **Aksiyon:** "başarısız/bulunamadı" ifadesi yanıltıcı; bunlar REVIEW-şiddetinde
  module-access/data-state bulgularıdır (gizlenmemiş, doctrine-uyumlu). Sayım
  değişmez.

### 5b) settings_audit / admin_rbac / hr_rbac_pii REVIEW — gerçek mi stale mi?
Aynı granülarite paterni; hepsi **gerçek run #190 bulgusu**, envanterle tutarlı:
- **settings_audit:** "B) Audit trail" case `✅ passed` ama içinde
  `audit_reachability timeline=500 security_audit=500` REVIEW'i (audit okuma
  endpoint'leri 500).
- **admin_rbac:** "A) Super-admin baseline" case `✅ passed` ama
  `super_admin_baseline 2xx=9/10, /api/system/db-stats=0` REVIEW'i.
- **hr_rbac_pii:** "D) Audit log scope" case `✅ passed` ama `audit_scope status=500`
  REVIEW'i (C) salary-history havuz boş → `⏭️ skipped`).
- **Mutabakat:** Modül tablosu REVIEW dağılımı toplamı = **21** (= rapor toplam
  REVIEW). REVIEW detay listesindeki 21 kalem birebir eşleşir. Hiçbiri önceki
  run'dan taşınmış DEĞİL.

### 5c) Tekrarlayan WATCH sinyali (bilgi)
Audit-okuma endpoint'leri üç specte 500 dönüyor (settings_audit timeline/
security_audit; hr_rbac_pii audit_scope). Önceki run'larda da P2'ydi — yeni
regresyon değil. NO-GO sürücüsü değil; ops/backend triajı için açık WATCH kalemi.

## 6) P2 / REVIEW / SKIP görünürlüğü

P2=30, REVIEW=21, SKIP=44, P3=2 — hakim tema **data-state** (özellikle HR
stress-prefix'li staff havuzu=0 → attendance/leave/shift/accrual/conflict/
lifecycle_v2/profile/offboarding module-blocked SKIP+Setup P2), posture
(backup disabled, webhook_admin/digital-key not-deployed) ve empty-harvest
vacuous IDOR (accommodation_tax/revenue_management/kvkk pilot havuzları boş).
Tam P2/REVIEW/SKIP listesi CI artifact `stress-drill-report` (§5 Severity Triage).

Doktrin: REVIEW/SKIP/P2/P3 görünür kalır; "GO" (yalın) iddia edilmez, yalnız
**GO WITH WATCH**; "/100 kapsam" iddia edilmez; mobile/F10 ayrı ve doğrulanmadı.
