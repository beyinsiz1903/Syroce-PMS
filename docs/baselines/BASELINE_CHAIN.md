# Stress Suite Baseline Chain

Bu dosya, web/backend Full Stress Suite'in resmi baseline zincirinin tek kayıt
kaynağıdır. **Yalnızca Run #196 mevcut (current) GREEN BASELINE'dır.** Diğer tüm
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

## Run #196 — CURRENT GREEN BASELINE

- **Tarih / deploy commit:** 2026-06-03, deploy commit `2582b14c` (post-#195
  REVIEW/SKIP Reduction pack merge'i içerir: finance_folio harvest `limit=5→50`,
  full_24h `maxPages 8→60`, admin db-stats per-sub-call guard + `degraded[]`).
  Murat tarafından manuel workflow_dispatch edildi.
- **Sonuç:** 708 test, conclusion=success, failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1590/0/21/11, P0=P1=0, P2=23 / P3=0, external_calls=[],
  pilot_drift=0, verdict **GO WITH WATCH**.
- **#195 → #196 DÜRÜST DELTA:** PASS **+20** (1570→1590), REVIEW **+6 ARTTI**
  (15→21), SKIP 11 SABİT, FAIL/P0/P1/P2/P3 SABİT, regresyon YOK. **Reduction
  hedefi TUTMADI** (projeksiyon SKIP→~9 / REVIEW→~12/13 yanlış çıktı). Kök neden
  (spin yok): (1) finance_folio + full_24h harvest fix'leri SKIP'li step'leri
  unblock etti ama bunlar by-design REVIEW yüzeylerine düştü (finance_folio A0/D
  409 open-folio/payment-perm; full_24h sabah_walkin n=25 ok=0 s400, oglen
  movement 0/3, procurement 422, aksam charge s400) → REVIEW net arttı. Revert
  EDİLMEDİ (skip-as-pass olurdu). (2) admin db-stats fix'i yanlış failure-mode
  hedefledi: gerçek sorun serverStatus 500 değil, per-collection collStats
  timeout/latency (admin_rbac super_admin_baseline db-stats status=0). Post-#196
  `asyncio.wait_for` latency-bound fix landed (canlı probe 200@8.5s; CI-pending
  #197), RBAC posture değişmedi.
- **DÜRÜST META-BULGU:** SKIP'i unblock ederek azaltmak REVIEW'i azaltmaz —
  unblock'lanan step by-design koşula çarpıp SKIP→REVIEW'e döner. Gerçek sayım
  düşüşü yalnızca gerçekten kırık şeyi onarmaktan veya meşru reclassify'dan gelir
  (by-design'lar reclassify EDİLEMEZ).
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26891329963
  (run #196, run ID 26891329963, event=workflow_dispatch).
- **Provenance:** anonim GitHub API'dan doğrulandı — head_sha=2582b14c,
  conclusion=success; artifacts stress-drill-report digest
  sha256:2018a4255f…, playwright-stress-report sha256:56f40a6b08…. Fabrike
  EDİLMEDİ (artifact gövdesi auth-gated → gövde re-sum CI-deferred; tutarlılık
  granülarite-modeli + operatör-rapor'a dayanır).
- **Rapor:** `attached_assets/Pasted-Full-Operational-Stress-Suite-CI-one-shot-F8A-F8B-F8C-F_1780505483439.txt`
  (#196 tam rapor, 1029 satır). Post-mortem:
  `docs/drill_reports/20260603_review_skip_reduction_post_run195.md`.

---

## Run #195 — historical reference

- **Tarih / commit:** 2026-06-03, commit `a3d43a1cf71dbda61b9795539da127e845727974`
  ("Published your App" — WATCH Reduction Pack'i içerir: parent commit
  `c40c277f` `/api/security/audit-logs` + `/api/hr/staff` encode-500 hardening
  (`backend/common/json_safe.py`) + Room QR submit rate-limit/auth reorder +
  tenant-scoped limiter key).
- **Sonuç:** 708 test, status=Success (conclusion=success), failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1570/0/15/11, P0=P1=0, P2=23 / P3=0,
  external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict
  **GO WITH WATCH**.
- **#194 → #195 delta:** PASS +5, REVIEW −2, P2 −1; SKIP/FAIL/P0/P1/P3 sabit.
  Temiz, pozitif, regresyonsuz ilerleme. WATCH pack kanıtı: #194'te görünen
  audit-logs 500 ve hr/staff 500 yüzeyleri #195 P2/REVIEW listelerinde ARTIK
  YOK (T001+T002 landed). Not: rate_limit_boundary P2 sürüyor ama detay
  `qr_submit: skipped no_room` → T003'ün QR fix'i bu run'da stress-exercise
  EDİLMEDİ (yalnızca canlı probe ile doğrulandı); kalan finding ayrı bir yüzey
  olan `auth_login` burst'üdür (0 throttled — login-throttle ordering, yeni WATCH
  adayı). activity-PII (T004) by-design olarak sürüyor (beklenen).
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26879084806
  (run #195, run ID 26879084806, job ID 79274137231, event=workflow_dispatch,
  run_attempt=1, branch main, süre ~70dk / 1h10m8s).
- **Artifacts (2) — provenance TAM (GitHub Actions API `digest` alanından doğrulandı, fabrike EDİLMEDİ):**
  - stress-drill-report (30547 B) —
    sha256:`d67b9615cf547531da2abc532f7afc3f8a84602aff4884a8fae133e5b67de228`.
  - playwright-stress-report (809220 B) —
    sha256:`83160fb57dd4ba012a5ea9b68a5057f28fda157bef692124e4c02fb8deed36c5`.
- **Yöntem dürüstlüğü:** run/job/artifact metadata anonim public GitHub API'dan
  doğrulandı (head_sha=a3d43a1c, conclusion=success). Artifact ZIP gövdesi
  auth-gated → #195 gövde REVIEW-toplamı bu oturumda satır-satır re-türetilmedi;
  sınıflandırma operatör raporu + granülarite-modeli + #190 §5'e dayanır.
- **Drill:** `docs/drill_reports/20260603_stress_full_stress_suite_GREEN_708test_run195.md`.
- **Post-#195 REVIEW/SKIP Reduction (Option 1, CI-pending; baseline DEĞİŞMEZ):**
  3 doctrine-safe fix (finance_folio harvest `limit=5→50`; full_24h `maxPages 8→60`
  helper safety-net override; admin db-stats 500-hardening guarded 200+`degraded[]`)
  + housekeeping cold-boot TTI JUSTIFY (index fake-green) + ~22 by-design/irreducible
  tek tek gerekçeli. Beklenen modest düşüş SKIP 11→~9, REVIEW 15→~12/13 (SIFIR DEĞİL);
  nihai delta sonraki full stress workflow_dispatch ile doğrulanır (agent dispatch
  ETMEZ). Drill: `docs/drill_reports/20260603_review_skip_reduction_post_run195.md`.

---

## Run #194 — historical reference (önceki current; #195 promote'unda indirildi)

- **Tarih / commit:** 2026-06-03, commit `9f4b3a74d894f52464e2f0f6a0037387df58f636`
  ("Update test performance budget to account for increased data size" — seed perf
  budget 30s→45s recalibration; bu zincirde folio detail + audit timeline + folio
  activities/operations 500 fix'leri merge edilmiştir).
- **Sonuç:** 708 test, status=Success (conclusion=success), failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1565/0/17/11, P0=P1=0, P2=24 / P3=0,
  external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict
  **GO WITH WATCH**.
- **#190 → #194 delta:** PASS +94, REVIEW −4, SKIP −33, P2 −6, P3 −2;
  FAIL/P0/P1 sabit 0. Güçlü pozitif ilerleme (folio-mass void, HR modülleri,
  settings_audit artık temiz koşuyor); regresyon yok. En değerli kazanım SKIP 44→11.
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26869789889
  (run #194, run ID 26869789889, job ID 79241995727, event=schedule, branch main).
- **Artifacts (2) — provenance TAM (GitHub Actions API `digest` alanından doğrulandı, fabrike EDİLMEDİ):**
  - stress-drill-report — ID `7379444307` (30627 B) —
    sha256:`346dec0216b6e00257c4a0c1972317ba411b158ff970e239c2888ed39cf0996f`.
  - playwright-stress-report — ID `7379443979` (808734 B) —
    sha256:`5a59046a3245be53bfb4f647dc6a12f21b7c4f0400466c62b5bdeae50c75507e`.
- **Seed perf notu:** #194 seed total=26097.7ms eski 30s eşiğini de geçer →
  #194 yeşili budget 30s→45s değişikliğine BAĞLI DEĞİL.
- **Tutarlılık doğrulaması:** Murat'ın 3 maddesi (settings_audit "audit marker not
  found", reservation_deep waitlist/city-ledger, finance_folio 409) granülarite
  artefaktı / legitimate harness annotation'dır (modül-tablosu adım ekseni ≠
  severity-triage ekseni); stale carryover DEĞİL. Yöntem dürüstlüğü: artifact ZIP
  gövdesi auth-gated (401) → #194 gövde REVIEW-toplamı bu oturumda satır-satır
  re-türetilemedi; sınıflandırma granülarite-modeli + #190 §5 (aynı yapı satır-satır
  doğrulanmış) + operatör-transkript sayılarına dayanır. Detay → drill §5.
- **Drill:** `docs/drill_reports/20260603_stress_full_stress_suite_GREEN_708test_run194.md`.

---

## Run #190 — historical reference (önceki current; #194 promote'unda indirildi)

- **Tarih / commit:** 2026-06-02, commit `adfa87d39f91bac5221247217f89d3207a08ab4a`
  ("Published your App" — messaging `/send` graceful-delivery 5xx guard + HR
  RBAC/PII spec-36 false-RED fix içerir).
- **Sonuç:** 708 test, status=Success, failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1471/0/21/44, P0=P1=0, P2=30 / P3=2 informational,
  external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict
  **GO WITH WATCH**.
- **#184 → #190 delta:** PASS +31, REVIEW +2, SKIP −10, P2 −1; FAIL/P0/P1 sabit 0.
  Pozitif ilerleme (önceden module-blocked/atlanan yüzeyler artık koşuyor);
  regresyon yok. REVIEW +2 data-state varyansı.
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26819935740
  (run #190, run ID 26819935740, job ID 79071540497, branch main).
- **Artifacts (2) — provenance TAM (GitHub Actions API `digest` alanından doğrulandı, fabrike EDİLMEDİ):**
  - stress-drill-report — ID `7359234557` (31639 B) —
    sha256:`827b360b95d91d78d02d9571fadbb7b92e91bc96cc43707d381fb3817df15454`.
  - playwright-stress-report — ID `7359234213` (794962 B) —
    sha256:`6a7dedefd75d9d2f490410ed2c48a5fc3e8d28291caf6d8c10651d279a3079e1`.
- **Tutarlılık doğrulaması:** reservation_deep (waitlist/city-ledger) + settings_audit/
  admin/HR REVIEW kalemleri GERÇEK run #190 bulgularıdır (modül tablosu REVIEW
  toplamı = 21 birebir mutabık); stale triage carryover DEĞİL. Envanter "passed" =
  Playwright case-seviyesi (hard-throw yok); REVIEW = harness adım-içi annotation
  (module-access 403 / data-state). Detay → drill §5.
- **Drill:** `docs/drill_reports/20260602_stress_full_stress_suite_GREEN_708test_run190.md`.

---

## Run #184 — historical reference

- **Tarih / commit:** 2026-06-01, commit `1055e6848aa047a3f8d46d5f5d05cde145d2b3fc`.
- **Sonuç:** 708 test, status=Success, failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1440/0/19/54, P0=P1=0, P2=31 / P3=2 informational,
  external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict
  **GO WITH WATCH** (metrikler operatör raporundan; CI conclusion=success doğrulandı).
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26771158900
  (run #184, run ID 26771158900, job ID 78910688457, branch main).
- **Artifacts (2) — provenance TAM (GitHub Actions API `digest` alanından doğrulandı):**
  - stress-drill-report — ID `7339879559` (32351 B) —
    sha256:`d21e9c5ad6be7731479e5994f99236a8118f94e3dc0397e65914c6a381d9bf74`.
  - playwright-stress-report — ID `7339879193` (788756 B) —
    sha256:`ebc0cb3b4cd3a26ce69cd2b0d278b6d5028680ebcadafaec2b0a6202e92b34ac`.
- **Drift notu:** #184 operatör tarafından current baseline sayıldı ama bu zincir
  ve `replit.md` o tarihte hiç #184'e güncellenmedi (docs #171'de kaldı). Bu kayıt
  ilk kez backfill'dir; provenance CI'dan doğrulandı, fabrike EDİLMEDİ. #190
  promote'u sırasında historical'a alındı.

---

## Run #171 — historical reference (önceki current; #190 promote'unda indirildi)

- **Tarih / commit:** 2026-05-31, commit `b6c61862be61d111a5f725c786073fa57f35276f`
  ("Published your App" — Post-#170 Minimal Fix Pack'i içerir: e-Fatura VKN spec
  fix + housekeeping selector-not hizalama).
- **Sonuç:** 703 test, status=Success, failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1384/0/48/43, P0=P1=0, P2=56 / P3=1 informational,
  external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict
  **GO WITH WATCH**.
- **#168 → #171 delta:** Toplam +1, PASS +2, P2 −1; FAIL/REVIEW/SKIP/P0/P1 aynı.
  Temiz ve pozitif ilerleme; regresyon yok. e-Fatura test verisi düzeltmesi
  karşılığını verdi → `accounting_expenses` artık tamamen temiz
  (10 PASS / 0 REVIEW / 0 SKIP).
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26708567911
  (run #171, run ID 26708567911, job ID 78714440738, branch main).
- **Artifacts (2) — provenance TAM (CI'dan doğrulandı, fabrike EDİLMEDİ):**
  - stress-drill-report — ID 7315902501 —
    sha256:`142d294eaab0eead173d5f730503d9f6540b5d5a65a4ea10e61b6af9bb015152`.
  - playwright-stress-report — ID 7315902360 —
    sha256:`25cd75d903b0015f7bc8816a78a9ee4c1ab78703bd27182f3282a8c37d87f899`.
- **Drill:** `docs/drill_reports/20260531_stress_full_stress_suite_GREEN_703test_run171.md`.

---

## Run #168 — historical reference

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

## Run #170 — post-packages verification run (NOT baseline)

- **Tarih / commit:** 2026-05-30, commit `b3d3bdb` (HEAD "Published your App").
- **Sonuç:** 702 test, status=Success, failedTests=0,
  PASS/FAIL/REVIEW/SKIP=1380/0/50/43, P0=P1=0, P2=57 / P3=1 informational,
  external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict **GO WITH WATCH**.
- **Promote? HAYIR.** #168'den daha iyi değil (REVIEW +2, PASS −2, P2 aynı). O tarihte #168
  current GREEN BASELINE olarak kaldı (sonradan #171→#184→#190; artık #190 current); #170 yalnızca paket A+B/C/D/E/F sonrası doğrulama run'ıdır.
- **Provenance:** #168 (`52575268`) Package C/D/E/F'in hepsinden ÖNCE; #170 hepsini İÇERİR
  (zincir: `52575268`→C`5c858cbe`→D`76f57095`→E`12452add`→F`443b2093`→docs`0daab6ec`→#170`b3d3bdb`).
  Delta gerçekten paket etkisini ölçer.
- **Delta analizi & sınıflandırma:** `docs/drill_reports/20260531_post_run170_delta_review.md`
  (kalan açıklar: çoğu OPERATOR-ENV; e-Fatura + housekeeping-not SPEC-DRIFT; folio void-charge
  teşhis-bekler).
- **Post-#170 Minimal Fix Pack (SPEC-DRIFT, kod CI'da doğrulanmadı — baseline taşımaz):**
  `docs/drill_reports/20260531_post_run170_minimal_fix_candidate.md`. e-Fatura spec
  customer_tax_number → geçerli 10-hane VKN + B2 strict-validator assertion (backend validator
  DEĞİŞMEDİ); housekeeping selector-miss notu test-scope `candidates` + `/housekeeping-status`
  route'una hizalandı (status ladder / TTI gate DEĞİŞMEDİ). Folio C4 KOD DEĞİŞTİRİLMEDİ
  (path+shape doğru; charges_empty ayrımı CI detailShapeSnap gerektirir). O tarihte #168 current GREEN
  BASELINE olarak kaldı; bu Minimal Fix Pack'in etkisi sonradan **Run #171 full stress ile doğrulandı** (o tarihte current; current artık #190).

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
