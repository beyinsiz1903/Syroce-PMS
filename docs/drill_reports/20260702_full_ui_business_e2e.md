# Full UI + Business E2E — 20260702

> Suite: `frontend/e2e-business/` (Playwright). Üretildi: 2026-07-02T10:13:03.013Z

## 1. Yönetici özeti

- Toplam test: **1**
- Başarısız test: **1**
- Adım sayaçları: PASS=6 | FAIL=1 | REVIEW=0 | SKIP=0
- Süre: 18.8s
- Son karar: **NO-GO** — failedTests=1, FAIL adım=1

## 2. Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| reservation | 6 | 1 | 0 | 0 | 7 |

## 3. Kritik bulgular (FAIL adımlar + başarısız testler)

### ❌ [reservation] UI calendar conflict dialog flow
- Test: `desktop › 22-calendar-conflict-dialog.spec.js › Scope 3 — Booking conflict dialog (calendar create wiring) › E2E: Calendar empty-cell create 409 surfaces BookingConflictDialog`
- Endpoint: `-`  HTTP: `-`
- Not: error=locator.waitFor: Timeout 10000ms exceeded.
Call log:
[2m  - waiting for locator('[data-testid="booking-conflict-dialog"]').first() to be visible[22m


### ❌ Test failure — desktop › 22-calendar-conflict-dialog.spec.js › Scope 3 — Booking conflict dialog (calendar create wiring) › E2E: Calendar empty-cell create 409 surfaces BookingConflictDialog
- File: `frontend/e2e-business/22-calendar-conflict-dialog.spec.js`  Project: `desktop`  Süre: 16.0s
- Hata: TimeoutError: locator.waitFor: Timeout 10000ms exceeded.  Call log:  [2m  - waiting for locator('[data-testid="booking-conflict-dialog"]').first() to be visible[22m  
- Artifacts:
  - screenshot: `frontend/test-results-business/22-calendar-conflict-dialo-f1c33-faces-BookingConflictDialog-desktop/test-failed-1.png`
  - video: `frontend/test-results-business/22-calendar-conflict-dialo-f1c33-faces-BookingConflictDialog-desktop/video.webm`
  - error-context: `frontend/test-results-business/22-calendar-conflict-dialo-f1c33-faces-BookingConflictDialog-desktop/error-context.md`
  - trace: `frontend/test-results-business/22-calendar-conflict-dialo-f1c33-faces-BookingConflictDialog-desktop/trace.zip`

## 4. Test verileri (oluşturulan / temizlenen)

| Kind | Label | ID | Cleanup | Endpoint |
|---|---|---|---|---|
| booking | E2E_mr3cj9vspzgh_GUEST | ce4acb5a-907a-467b-a3d3-1b632faa0f9a | pending | /api/pms-core/cancel |
| booking | E2E_mr3cj9vspzgh_GUEST 2 | 473127cb-d919-47a0-a730-4d555edd5f1d | pending | /api/pms-core/cancel |
| booking | E2E_mr3cj9vspzgh_GUEST (cancelled) | ce4acb5a-907a-467b-a3d3-1b632faa0f9a | completed | /api/pms-core/cancel |

## 5. REVIEW + SKIP adımlar

_Yok._

## 6. Risk sınıflandırması (heuristic)

- **P0 (canlıya çıkışı engeller)**: failedTests=1, FAIL adım=1
- **P1 (pilot öncesi düzeltilmeli)**: REVIEW kritik modüllerde — bkz. §5
- **P2 (pilot sonrası)**: secondary modül REVIEW/SKIP
- **P3 (kozmetik)**: console error allowlist dışı (varsa raporlandı)

## 7. Artifact path'leri

- HTML report: `frontend/playwright-business-report/`
- Trace/video/screenshot: `frontend/test-results-business/`
- Data registry: `frontend/e2e-business/.auth/data-registry.json`
- Auth state: `frontend/e2e-business/.auth/admin.json` (gitignore önerilir)

## 8. Test inventory

| # | Test | Project | Outcome | Süre |
|---:|---|---|---|---:|
| 1 | desktop › 22-calendar-conflict-dialog.spec.js › Scope 3 — Booking conflict dialog (calendar create wiring) › E2E: Calendar empty-cell create 409 surfaces BookingConflictDialog | desktop | ❌ failed | 16.0s |
