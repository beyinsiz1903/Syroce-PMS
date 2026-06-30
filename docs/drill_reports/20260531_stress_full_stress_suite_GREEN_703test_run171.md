# Full Stress Suite — GREEN BASELINE — Run #171 (2026-05-31)

> Bu doküman, web/backend Full Operational Stress Suite'in **resmi GREEN BASELINE**
> kaydıdır. Önceki resmi baseline Run #168 → historical reference'a indi.
> **Kapsam notu:** bu web/backend full stress suite baseline'ıdır, /100 uygulama
> kapsamı DEĞİLDİR — mobile/F10 ayrı ve açık (doğrulanmadı). Merkezi referans:
> `docs/TEST_COVERAGE_SCORECARD_100.md`.

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 703 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1384 / 0 / 48 / 43 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 56 / 1 |
| Final verdict | **GO WITH WATCH** — P2=56, REVIEW=48 |

Mutlak kurallar (hepsi korundu): pilot mutation=0, external_calls=[],
failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH, assertion gevşetme YOK,
skip-as-pass YOK. Düz "GO" iddiası YOK; "/100 kapsam" iddiası YOK.

## 2) Provenance

- **Tarih:** 2026-05-31
- **Run:** #171, status=Success
- **Run ID:** 26708567911
- **Job ID:** 78714440738
- **Commit (run koştuğu):** `b6c61862be61d111a5f725c786073fa57f35276f`
  ("Published your App" — Post-#170 Minimal Fix Pack'i içerir: e-Fatura VKN spec
  fix + housekeeping selector-not hizalama).
- **Branch:** main
- **Run URL:** https://github.com/beyinsiz1903/syroce-pms/actions/runs/26708567911
- **GitHub job durumu:** completed/success — full stress step + drill report
  verification + artifact upload adımlarının hepsi başarılı.
- **Artifacts (2) — provenance TAM (CI'dan doğrulandı):**
  - stress-drill-report — ID `7315902501` —
    `sha256:142d294eaab0eead173d5f730503d9f6540b5d5a65a4ea10e61b6af9bb015152`
  - playwright-stress-report — ID `7315902360` —
    `sha256:25cd75d903b0015f7bc8816a78a9ee4c1ab78703bd27182f3282a8c37d87f899`

> #168'in aksine #171 provenance'ı eksiksizdir (job ID + her iki artifact numeric
> ID + tam sha256 digest CI'dan doğrulandı). Hiçbir alan fabrike EDİLMEDİ.

## 3) Run-level garantiler

- **external_calls:** `[]`
- **pilot_drift:** 0 (pilot mutation yok)
- **cleanup#2 idempotent:** true

## 4) Run #168 → #171 delta

### Kod delta
- #171, Post-#170 Minimal Fix Pack'i içeren `b6c61862` ("Published your App")
  üzerinde koştu. Pack'in görünür etkisi: e-Fatura test verisi düzeltmesi
  (`accounting_expenses` artık tamamen temiz: **10 PASS / 0 REVIEW / 0 SKIP**).

### Test-yüzeyi delta
| Metrik | #168 | #171 | Delta |
|---|---|---|---|
| Toplam test | 702 | 703 | +1 |
| PASS | 1382 | 1384 | +2 |
| FAIL | 0 | 0 | — |
| REVIEW | 48 | 48 | — |
| SKIP | 43 | 43 | — |
| P2 | 57 | 56 | −1 |
| P3 | 1 | 1 | — |
| P0 / P1 | 0 / 0 | 0 / 0 | — |

**Atıf:** Büyük bir düşüş değil ama **temiz ve pozitif bir ilerleme**. e-Fatura
test verisi düzeltmesi karşılığını verdi (accounting_expenses temiz). FAIL/REVIEW/
SKIP sabit, P0/P1=0; regresyon yok.

## 5) P2 / REVIEW / SKIP görünürlüğü

P2=56, REVIEW=48, SKIP=43, P3=1 — kalemler önceki dalgalarla (Wave 6–9 +
Package A+B→F) aynı kategorilerde duruyor. Tam P2/REVIEW/SKIP listesi için CI
artifact `stress-drill-report` (§5 Severity Triage) ve önceki triage dokümanları:
- `docs/STRESS_P2_REVIEW_TRIAGE_20260526.md`
- `docs/drill_reports/20260530_review_skip_reduction_package_ab_inventory.md`
- `docs/drill_reports/20260531_post_run170_delta_review.md`

Doktrin: REVIEW/SKIP/P2/P3 görünür kalır; "GO" (yalın) iddia edilmez, yalnız
**GO WITH WATCH**; "/100 kapsam" iddia edilmez; mobile/F10 ayrı ve doğrulanmadı.
