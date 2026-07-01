# Drill — Full Stress Suite GREEN baseline (Run #167, 2026-05-30)

## Verdict

✅ **GREEN — GO WITH WATCH** (GO DEĞİL). Yeni official web/backend full stress
baseline. Run #162 historical reference'a düşürüldü.

**Bu /100 uygulama kapsamı DEĞİLDİR.** Mobile (F10) coverage ayrı ve açık
(doğrulanmadı) — merkezi referans `docs/TEST_COVERAGE_SCORECARD_100.md`.

## Provenance

| Alan | Değer |
|---|---|
| Date | 2026-05-30 |
| Workflow | GitHub Actions — Full Stress Suite (one-shot) |
| Run | **#167** |
| Run URL | https://github.com/beyinsiz1903/syroce-pms/actions/runs/26687012176 |
| Run ID / Job ID | 26687012176 / 78656853578 |
| Branch | `main` |
| Commit SHA | `0b99607fe3a64a7ada660d1f1bcb8607bd47f5dd` |
| Status | Success |
| Artifacts | stress-drill-report ID 7309449913, digest `sha256:7a4d424aac978ba3adeed1851d911545196e0fd46c773616b176f20960e3a46d` · playwright-stress-report ID 7309449854, digest `sha256:288544edb3ada9c2a001559a2aadc4fae1c4c198b35a8024f1fffd1107ade622` |

## Metrikler

| Metrik | Değer |
|---|---|
| Toplam test | **702** |
| failedTests | **0** |
| Adım PASS / FAIL / REVIEW / SKIP | **1379 / 0 / 48 / 44** |
| P0 / P1 / P2 / P3 | **0 / 0 / 58 / 1** |
| `external_calls_made` | `[]` ✓ |
| `pilot_drift` | 0 ✓ |
| Cleanup#2 idempotent | ✅ true |
| Final verdict | ✅ **GO WITH WATCH** — P2=58 REVIEW=48 SKIP=44 P3=1 (downgrade YOK; doktrin ≥ GO WITH WATCH karşılanıyor) |

## Run #162 → #167 değişimi

Tek değişiklik: **ai_pricing recommend-rates deterministik 500 fix** (pilot kirli
`base_price` verisi). `43-ai-pricing C) cross_tenant_pricing` artık PASS.
- Adım FAIL: 1 → **0**.
- Adım PASS: 1378 → **1379** (önceki NO-GO run @26ff329 ile kıyas).
- ai_pricing modülü: 20/1/0/0 → **21/0/0/0**.
- Diğer invariantlar korundu: failedTests=0, P0=P1=0, external_calls=[],
  pilot_drift=0, cleanup#2 idempotent.

Fix detayı: `docs/drill_reports/20260530_ai_pricing_recommend_rates_500_fix.md`.

## Açık kalemler (downgrade YOK, görünür tutulur)

- **P2 = 58** — operasyonel/data-state/by-design REVIEW kalemleri (folio-mass
  data-state, night-audit exceptions, graphql introspection prod, b2b per-subrouter
  scope, vb.). Hiçbiri P0/P1 değil.
- **REVIEW = 48** — module-blocked / endpoint-absent / env-posture (skip-as-pass
  DEĞİL).
- **SKIP = 44** — module-blocked doctrine (PASS sayılmaz).
- **P3 = 1** — informational.

## Kapsam notu

Bu baseline **web/backend full stress suite** içindir; **/100 uygulama kapsamı
DEĞİLDİR**. Mobile/F10 ayrı ve doğrulanmadı. Verdict **GO WITH WATCH** (GO
değildir).
