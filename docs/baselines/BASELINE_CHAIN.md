# Stress Suite Baseline Chain

Bu dosya, web/backend Full Stress Suite'in resmi baseline zincirinin tek kayıt
kaynağıdır. **Yalnızca Run #168 mevcut (current) GREEN BASELINE'dır.** Diğer tüm
run'lar tarihsel referanstır (historical reference) — provenance ve metrikler
korunur ama "current/official baseline" DEĞİLDİR.

> Kapsam notu: Bu web/backend full stress suite baseline'ıdır, **/100 uygulama
> kapsamı DEĞİLDİR** — mobile/F10 ayrı ve açıktır (doğrulanmadı). Merkezi kapsam
> referansı: `docs/TEST_COVERAGE_SCORECARD_100.md`.

## Her fazda mutlak kurallar

pilot mutation=0 · external_calls=[] · failedTests=0 · P0=P1=0 · verdict ≥ GO WITH
WATCH · assertion gevşetme YOK · skip-as-pass YOK. Asla düz "GO" veya "/100" iddiası
yok.

---

## Run #168 — CURRENT GREEN BASELINE

- **Tarih / commit:** 2026-05-30, commit `52575268c025d97ce67b409d187b041283c74064`
  (güncel HEAD `9e9796d1` yalnız import-sort/ruff I001 farkı — davranış değişikliği yok).
- **Sonuç:** 702 test, status=Success, failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1382/0/48/43, P0=P1=0, P2=57 / P3=1 informational,
  external_calls=[], pilot_drift=0, cleanup#1 deleted_total=7761 / cleanup#2
  deleted_total=0 idempotent=true, seed prefix `E2E_STRESS_F7_1780162874355_`
  (room_count=500), verdict **GO WITH WATCH**.
- **Run #167→#168 kod delta:** Exely pull worker transient-DB Sentry-noise guard
  (`TransientFailureTracker`, commit `52575268`) + webhook/payment reconciliation
  güvenlik commit'i (`ef7fac1f`) + publish (`78bef111`). Test-yüzeyi delta (PASS +3 /
  SKIP −1 / P2 −1) data-state varyansıdır, koda atfedilmez (Exely pull worker arka
  plan işçisi, HTTP test yüzeyinde görünmez; regresyon yok).
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26690524113
  (run #168, run ID 26690524113, branch main).
- **Artifacts (2):** playwright-stress-report (754KB,
  sha256:`cf37bf93d5f570e442ac962c9dac50149b21454acb0486c031723c9ea705c8e4`) +
  stress-drill-report (37.5KB, sha256 ekran görüntüsünde truncated).
- **Provenance uyarısı:** job ID + artifact numeric ID'leri + stress-drill-report tam
  sha256 ekran görüntüsünde yoktu → CI run sayfasından doğrulanmalı, fabrike EDİLMEDİ.
- **Drill:** `docs/drill_reports/20260530_stress_full_stress_suite_GREEN_702test_run168.md`.

---

## Run #167 — historical reference

- 2026-05-30, commit `0b99607fe3a64a7ada660d1f1bcb8607bd47f5dd`,
  PASS/FAIL/REVIEW/SKIP=1379/0/48/44, P2=58/P3=1, verdict GO WITH WATCH.
- Run URL: https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26687012176
  (run ID 26687012176, job ID 78656853578).
- Artifacts: stress-drill-report ID 7309449913 + playwright-stress-report ID 7309449854.
- Drill: `docs/drill_reports/20260530_stress_full_stress_suite_GREEN_702test_run167.md`
  (Run #162→#167 fix detayı: `docs/drill_reports/20260530_ai_pricing_recommend_rates_500_fix.md`).

## Run #162 — historical reference

- 2026-05-29, 702 test, commit `bde7662744c9b94a5c9294fa778202d813319dfc`,
  PASS/FAIL/REVIEW/SKIP=1316/0/46/61, P2=60/P3=1, verdict GO WITH WATCH.
- Run URL: https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26653464472
  (run ID 26653464472, job ID 78557501168).
- Artifacts: stress-drill-report ID 7298692917 + playwright-stress-report ID 7298692578.
- Drill: `docs/drill_reports/20260529_stress_full_stress_suite_GREEN_702test.md`.

## Run #161 — historical reference

- 2026-05-29, 702 test, commit `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`,
  P2=65/REVIEW=48/P3=1, verdict GO WITH WATCH.
- Run URL: https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26641150604
  (run ID 26641150604, job ID 78514272098).
- Artifacts: stress-drill-report ID 7293609890 + playwright-stress-report ID 7293609632.
- provenance+metrics drill comparison block'ta korunmuştur
  (`docs/drill_reports/20260529_stress_full_stress_suite_GREEN_702test.md`).

## Run #159 — historical reference

- 2026-05-28, 702 test, commit `e23a4ec603cc32984b741d77d67d57a0abba698b`,
  P2=65/P3=1, verdict GO WITH WATCH.
- Drill: `docs/drill_reports/20260528_stress_full_stress_suite_GREEN_702test.md`.

## Run #143 — oldest historical reference

- 2026-05-26, 84 spec / 556 test, commit `3b3891d`, P2=60/P3=1, verdict GO WITH WATCH.
- F8AH iki-tur kapatma: Tur 1 (commit `94514e6`) 4 P1 (konaklama amount/nights Pydantic
  `le=1e9/3650`, KDS terminal-state 409, KDS idempotency Mongo unique + 503); Tur 2
  (commits `147266d4` + `67374954` + `8f7f77b6`) P0 TWOFA throttle — Mongo-backed
  cross-instance throttle (`backend/security/auth_throttle.py`) + per-user_id layered
  throttle (`backend/routers/auth.py`, JWT-trusted, IP rotation immune, `consumed_jtis`
  insert ÖNCESI).
- Drill: `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md`.
  Coverage gap: `docs/STRESS_COVERAGE_GAP_REPORT_20260526.md`.
