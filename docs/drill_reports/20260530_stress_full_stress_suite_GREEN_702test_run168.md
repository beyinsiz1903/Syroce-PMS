# Full Stress Suite — GREEN BASELINE — Run #168 (2026-05-30)

> Bu doküman, web/backend Full Operational Stress Suite'in **resmi GREEN BASELINE**
> kaydıdır. Önceki resmi baseline Run #167 → historical reference'a indi.
> **Kapsam notu:** bu web/backend full stress suite baseline'ıdır, /100 uygulama
> kapsamı DEĞİLDİR — mobile/F10 ayrı ve açık (doğrulanmadı). Merkezi referans:
> `docs/TEST_COVERAGE_SCORECARD_100.md`.

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 702 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1382 / 0 / 48 / 43 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 57 / 1 |
| Süre | 3792.2s |
| Final verdict | **GO WITH WATCH** — P2=57, REVIEW=48 |

Mutlak kurallar (hepsi korundu): pilot mutation=0, external_calls=[],
failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH, assertion gevşetme YOK,
skip-as-pass YOK.

## 2) Provenance

- **Tarih:** 2026-05-30T17:39:48.535Z
- **Run:** #168, status=Success, süre 1h 4m 8s
- **Commit (run koştuğu):** `52575268c025d97ce67b409d187b041283c74064`
  ("Improve error logging for transient database issues")
- **Güncel HEAD:** `9e9796d1` ("Organize imports in exely pull worker file") —
  Run #168 commit'inden yalnız import-sort / ruff I001 farkı; **davranış
  değişikliği yok**, metrikler güncel HEAD için de geçerli.
- **Branch:** main
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26690524113
- **Run ID:** 26690524113
- **Artifacts (2):**
  - playwright-stress-report — 754KB —
    `sha256:cf37bf93d5f570e442ac962c9dac50149b21454acb0486c031723c9ea705c8e4`
  - stress-drill-report — 37.5KB — sha256 ekran görüntüsünde truncated

### Provenance boşlukları (fabrike EDİLMEDİ — CI run sayfasından doğrulanmalı)
- **job ID** — ekran görüntüsünde yoktu.
- **artifact numeric ID'leri** (her iki artifact) — ekran görüntüsünde yoktu.
- **stress-drill-report tam sha256** — ekran görüntüsünde kesikti.

"No fake-green" doktrini gereği bu alanlar tahmin edilmedi; operatör CI run
sayfasından tamamlayabilir.

## 3) Seed / Cleanup snapshot

- **Seed prefix:** `E2E_STRESS_F7_1780162874355_`, room_count=500
- **Seed counts:** rooms=500 guests=500 bookings=500 folios=500 charges=1750
  rnl=1250 hk=500
- **Seed timing_ms:** factory=90.6 insert=24537.8 total=24628.4
- **external_calls_made:** `[]`
- **tenant_context_used:** `true`
- **gates:** env_stress_tid_present / target_matches_stress_tid /
  pilot_tid_not_targeted / destructive_stress_allowed / external_dry_run = hepsi true
- **cleanup#1:** status=200 deleted_total=7761 ms=14609.2
- **cleanup#2_idempotent:** status=200 deleted_total=0 ms=10815.6 idempotent=true
- **pilot_diff:** baseline_bookings=30 after_bookings=30 **drift=0**

## 4) Run #167 → #168 delta

### Kod delta (commit'ler arası)
- `52575268` — Exely pull worker transient-DB Sentry-noise guard
  (`TransientFailureTracker` — `core/transient_db_guard.py` deseni, ~11 worker'da
  yerleşik). Bu oturumun ana işi.
- `ef7fac1f` — webhook/payment reconciliation güvenlik commit'i (önceki tur).
- `78bef111` — publish.

### Test-yüzeyi delta
| Metrik | #167 | #168 | Delta |
|---|---|---|---|
| PASS | 1379 | 1382 | +3 |
| FAIL | 0 | 0 | — |
| REVIEW | 48 | 48 | — |
| SKIP | 44 | 43 | −1 |
| P2 | 58 | 57 | −1 |
| P3 | 1 | 1 | — |

**Atıf:** Bu küçük oynamalar (PASS +3 / SKIP −1 / P2 −1) **data-state varyansıdır,
koda atfedilemez.** Exely pull worker bir arka plan işçisidir ve stress suite'in
test ettiği HTTP endpoint yüzeyinde görünmez; folio-mass charges tüketimi vb.
data-state farkları run-to-run normal dalgalanmadır. Net sonuç: **regresyon yok**,
fix temiz indi.

## 5) P2 / REVIEW / SKIP görünürlüğü

P2=57, REVIEW=48, SKIP=43, P3=1 — kalemler önceki dalgalarla (Wave 6–9 +
Package A+B) aynı kategorilerde duruyor; bu run zeroing programını ilerletmedi
(yalnız Exely Sentry-noise fix + baseline tazeleme). Tam P2/REVIEW/SKIP listesi
için CI artifact `stress-drill-report` (§5 Severity Triage) ve önceki triage
dokümanları:
- `docs/STRESS_P2_REVIEW_TRIAGE_20260526.md`
- `docs/drill_reports/20260530_review_skip_reduction_package_ab_inventory.md`
- `docs/drill_reports/20260530_review_skip_reduction_package_ab_candidate.md`

Doktrin: REVIEW/SKIP/P2/P3 görünür kalır; "GO" (yalın) iddia edilmez, yalnız
**GO WITH WATCH**; "/100 kapsam" iddia edilmez.
