# Full Stress Suite — GREEN BASELINE — Run #194 (2026-06-03)

> Bu doküman, web/backend Full Operational Stress Suite'in **resmi GREEN BASELINE**
> kaydıdır. Önceki resmi baseline Run #190 → historical reference'a indi.
> **Kapsam notu:** bu web/backend full stress suite baseline'ıdır, /100 uygulama
> kapsamı DEĞİLDİR — mobile/F10 ayrı ve açık (doğrulanmadı). Merkezi referans:
> `docs/TEST_COVERAGE_SCORECARD_100.md`.

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 708 |
| Başarısız test | 0 |
| Adım PASS / FAIL / REVIEW / SKIP | 1565 / 0 / 17 / 11 |
| P0 / P1 / P2 / P3 finding | 0 / 0 / 24 / 0 |
| Final verdict | **GO WITH WATCH** — P2=24, REVIEW=17, SKIP=11 |

Mutlak kurallar (hepsi korundu): pilot mutation=0, external_calls=[],
failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH, assertion gevşetme YOK,
skip-as-pass YOK. Düz "GO" iddiası YOK; "/100 kapsam" iddiası YOK; mobile/F10 ayrı.

## 2) Provenance

- **Tarih:** 2026-06-03
- **Run:** #194, event=schedule, status=completed, conclusion=**success**
- **Run ID:** 26869789889
- **Job ID:** 79241995727 ("Full stress suite (one-shot)", conclusion=success)
- **Commit (run koştuğu):** `9f4b3a74d894f52464e2f0f6a0037387df58f636`
  ("Update test performance budget to account for increased data size" — seed perf
  budget 30s→45s recalibration; ayrıca bu zincirde folio detail + audit timeline +
  folio activities/operations 500 fix'leri merge edilmiştir).
- **Branch:** main
- **Job süresi:** 2026-06-03T07:18:47Z → 08:27:57Z (~1s 9dk; ekran görüntüsü
  "1h 9m 14s" toplam süre ile uyumlu).
- **Run URL:** https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26869789889
- **Artifacts (2) — provenance TAM (GitHub Actions API `digest` alanından doğrulandı, fabrike EDİLMEDİ):**
  - stress-drill-report — ID `7379444307` (30627 B) —
    `sha256:346dec0216b6e00257c4a0c1972317ba411b158ff970e239c2888ed39cf0996f`
  - playwright-stress-report — ID `7379443979` (808734 B) —
    `sha256:5a59046a3245be53bfb4f647dc6a12f21b7c4f0400466c62b5bdeae50c75507e`

> Hiçbir provenance alanı fabrike EDİLMEDİ. Run/job ID'leri ve artifact sha256
> digest'leri GitHub REST API'den (public repo, anonim — `GITHUB_TOKEN` gerekmedi)
> okundu; conclusion=success. Artifact ZIP **gövdesi** indirme `Requires
> authentication` (401) ile auth-gated'dır; yalnız metadata/`digest` anonim erişime
> açıktır (memory: `stress-provenance-github-digest.md`).

## 3) Run-level garantiler

- **external_calls:** `[]`
- **pilot_drift:** 0 (operatör raporu; pilot mutation yok)
- **cleanup#2 idempotent:** true
- **failedTests:** 0 · **P0 / P1:** 0 / 0 · **CI conclusion:** success

## 4) Run #190 → #194 delta

### Kod delta (bu zincirde merge edilenler)
1. **Folio detail + audit timeline + folio activities/operations 500 fix** —
   karışık-tip timestamp sort (datetime+str+None type-safe key) + encode-zamanı
   serialization (raw Mongo docs FastAPI encode'undan ÖNCE JSON-native sanitize).
   Audit-okuma 500'leri (timeline/security_audit/hr audit_scope) bu fix ile
   gerçek kök-neden düzeltmesi olarak kapanmıştır (gevşetme değil).
2. **Seed perf budget recalibration 30s→45s** — büyüyen deterministik seed
   payload'a göre yeniden hesaplama (aging room_night_locks/payments/charges + HR
   staff pool + mice). Bu budget değişikliği **#194 yeşilinin sebebi DEĞİLDİR**
   (bkz. §6).
3. Önceki REVIEW/SKIP reduction paketleri (A+B→F) ve module-blocked yüzeylerin
   gerçek koşulması (özellikle HR staff pool + folio void-charge/void-payment).

### Test-yüzeyi delta
| Metrik | #190 | #194 | Delta |
|---|---|---|---|
| Toplam test | 708 | 708 | — |
| PASS | 1471 | 1565 | +94 |
| FAIL | 0 | 0 | — |
| REVIEW | 21 | 17 | −4 |
| SKIP | 44 | 11 | −33 |
| P2 | 30 | 24 | −6 |
| P3 | 2 | 0 | −2 |
| P0 / P1 | 0 / 0 | 0 / 0 | — |

**Atıf:** Güçlü pozitif ilerleme — PASS +94, SKIP −33 (en değerli kazanım:
önceden module-blocked/atlanan yüzeyler — folio-mass void, HR modülleri,
settings_audit — artık gerçek koşuyor), P2 −6, P3 −2. FAIL/P0/P1=0 sabit;
regresyon yok.

### Operatör-transkript modül kazanımları (drill body operatör tarafından okundu)
- **folio-mass:** #190 14/4/0 (P3=2) → #194 18/0/0 (P3=0). Void-charge/void-payment toparlandı.
- **HR modülleri:** attendance 10/0/0, leave 10/0/0, shift 14/0/0, leave_accrual 17/0/0,
  shift_conflict 17/0/0, lifecycle_v2 14/0/0, employee_profile_detail 11/0/0,
  offboarding 11/0/0 — önceki "staff pool 0 / module blocked" büyük ölçüde çözüldü.
- **settings_audit:** 13/0/0 (audit 500 fix sonrası temiz).
- **housekeeping:** 17/1/0 — yalnız küçük soft cold-boot TTI (masaüstü 3102ms /
  mobil 3074ms, 3000ms eşiğini çok az aşan SOFT; hard breach YOK).

## 5) Rapor tutarlılık doğrulaması (promote öncesi — Murat'ın 3 maddesi)

Murat üç kalemin "gerçek harness annotation mı yoksa stale carryover mı" olduğunu
doğrulamamı istedi. **Yöntem dürüstlüğü:** artifact ZIP gövdesi auth-gated (401)
olduğundan #194 modül tablosunun REVIEW-toplamını bu oturumda **satır-satır
yeniden türetemedim**; aşağıdaki sınıflandırma (a) harness raporlama-granülarite
modeline ve (b) #190 §5'te aynı yapının satır-satır doğrulanmış olmasına ve (c)
operatör-transkript modül sayılarına dayanır. Agrega sayılar (REVIEW=17, P2=24,
SKIP=11) operatör raporundan + API conclusion=success ile tutarlıdır.

**Granülarite modeli (yapısal, run-bağımsız):** Stress raporunda iki AYRI eksen var:
1. **Modül tablosu** = Playwright **case/adım-seviyesi** PASS/REVIEW/SKIP (passed =
   hard-throw atılmadı).
2. **Severity triage** = harness **adım-içi** P0–P3 annotation'ları; bir case
   PASS sayılırken içinde soft bir P2/REVIEW notu taşıyabilir.
Bu yüzden "modül tablosu temiz (örn. 13/0/0) ama P2 listesinde bir kalem var"
bir ÇELİŞKİ DEĞİL — iki eksen farklı şeyleri sayar.

- **5a) settings_audit 13/0/0 ama P2 "audit marker not found":** Modül tablosu
  adım-seviyesinde 0 REVIEW/0 SKIP (audit 500 fix sonrası case'ler PASS). P2 ise
  ayrı severity eksenindeki soft bir bulgu (audit marker beklendiği yerde
  bulunamadı — case'i FAIL'a düşürmüyor). **Legitimate harness annotation; stale
  carryover DEĞİL** (audit 500'ler bu zincirde gerçek fix aldı; eğer stale olsa
  REVIEW/SKIP de taşırdı, 13/0/0 temiz).
- **5b) reservation_deep waitlist/city-ledger passed ama P2 annotation:** #190
  §5a'da satır-satır doğrulanan AYNI patern — case-seviyesi passed (hard-throw
  yok), harness module-access 403 / boş data-state (folios=0) durumunu adım-içi
  P2/REVIEW'a degrade eder. **Legitimate; stale DEĞİL** (booking ID'leri
  run-spesifik; data-state/module-access kaynaklı).
- **5c) finance_folio passed ama 409 annotation:** 409 = bir önceki specin
  force-checkout'u sonrası closed-folio guard'ın legitimate dönüşü (memory:
  `stress-folio-void-closed-guard.md`). Case PASS, 409 soft data-state
  annotation'ı. **Legitimate; stale DEĞİL.**

**Sonuç:** Üçü de granülarite-artefaktı / gerçek data-state-module-access
annotation'ı; stale triage carryover göstergesi YOK. Tam satır-satır #194-gövde
re-sum doğrulaması artifact auth açıldığında yapılabilir (CI-deferred); promote
gerekçesi buna bağlı değildir (§7).

## 6) Seed perf budget değişikliği — #194 yeşili buna BAĞLI DEĞİL

- Commit `9f4b3a7` seed perf budget'ı 30s → 45s yaptı (büyüyen payload recalibration).
- **#194 seed total = 26097.7ms** (operatör raporu) — bu değer **eski 30s eşiğini
  de geçiyor**. Yani #194'ün yeşil görünmesi threshold gevşetmesinden
  kaynaklanmıyor; aynı run eski budget altında da PASS verirdi.
- Recalibration gerekçesi (gross-blowup hâlâ yakalanır, gerçek `total_ms` her zaman
  kaydedilir, payload büyümesi sebebiyle): memory `stress-perf-budget-recalibration.md`.

## 7) Promote kararı

- Provenance TAM doğrulandı (API; conclusion=success; commit/run/job/artifact
  digest'leri fabrike EDİLMEDİ).
- Run-level garantiler karşılandı: failedTests=0, P0=P1=0, external_calls=[],
  pilot_drift=0, cleanup#2 idempotent=true.
- Delta #190'a göre güçlü pozitif (PASS +94, SKIP −33, P2 −6, P3 −2); regresyon yok.
- Rapor tutarlılığı: 3 madde granülarite/legitimate-annotation (§5); stale YOK.
- Verdict: **GO WITH WATCH** (düz "GO" değil; "/100" iddiası YOK; mobile/F10 ayrı).

→ **Run #194 yeni resmi web/backend GREEN BASELINE** (current). Run #190 historical
reference'a indirildi. Chain korunur: #190/#184/#171/#170/#168/#167/#162/#161/#159/#143.

## 8) Açık WATCH kalemleri (sonraki adaylar)

P2=24, REVIEW=17, SKIP=11 görünür kalır. Murat'ın işaret ettiği en net sıradaki
adaylar: night audit unresolved exception count (200), backup posture
(BACKUP_ENABLED), housekeeping soft cold-boot TTI, HR audit endpoint 500 (kalan),
notification activity-feed free-text PII, digital key route 404, reservation
waitlist/city-ledger annotations, rate limit public burst 429, finance folio 409
annotation, full 24h sim data scarcity. Tam liste: CI artifact `stress-drill-report`
(§ Severity Triage). Bunlar NO-GO sürücüsü DEĞİL; ops/backend WATCH kalemleri.
