# Full UI + Business E2E — 20260516

> Suite: `frontend/e2e-business/` (Playwright). Üretildi: 2026-05-16T15:31:05.054Z

## 1. Yönetici özeti

- Toplam test: **8**
- Başarısız test: **0**
- Adım sayaçları: PASS=20 | FAIL=0 | REVIEW=11 | SKIP=0
- Süre: 49.4s
- Son karar: **GO WITH WATCH** — REVIEW=11 adım — pilot sırasında manuel takip

## 2. Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| auth-nav | 7 | 0 | 2 | 0 | 9 |
| dashboard-health | 8 | 0 | 6 | 0 | 14 |
| security-rbac | 5 | 0 | 3 | 0 | 8 |

## 3. Kritik bulgular (FAIL adımlar + başarısız testler)

_Yok — tüm testler ve adımlar geçti veya REVIEW/SKIP olarak işaretli._

## 4. Test verileri (oluşturulan / temizlenen)

_Hiç entity oluşturulmadı veya kayıt bulunamadı._

## 5. REVIEW + SKIP adımlar

### REVIEW (11)
- **[auth-nav]** Sidebar nav linkleri — count=0 
- **[auth-nav]** Profil menü tetikleyici — - 
- **[dashboard-health]** Modül kartları (PMS/RMS) — pms=0 rms=0 
- **[dashboard-health]** Pilot kart: Readiness — count=0 
- **[dashboard-health]** Pilot kart: CM Outbox — count=0 
- **[dashboard-health]** Pilot kart: Circuit Breaker — count=0 
- **[dashboard-health]** Pilot kart: Atlas Backup — count=0 
- **[dashboard-health]** Pilot kart: Observability — count=0 
- **[security-rbac]** Sahte folio id 000000000000000000000000 — Complete Hotel Management Platform

🇬🇧 English
Welcome
Sign in to your account (`/folio-detail/000000000000000000000000` 200)
- **[security-rbac]** Sahte folio id aaaaaaaaaaaaaaaaaaaaaaaa — Complete Hotel Management Platform

🇬🇧 English
Welcome
Sign in to your account (`/folio-detail/aaaaaaaaaaaaaaaaaaaaaaaa` 200)
- **[security-rbac]** Sahte folio id invalid-id-format-xyz — Complete Hotel Management Platform

🇬🇧 English
Welcome
Sign in to your account (`/folio-detail/invalid-id-format-xyz` 200)

## 6. Risk sınıflandırması (heuristic)

- **P0 (canlıya çıkışı engeller)**: failedTests=0, FAIL adım=0
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
| 1 | desktop › 01-auth-nav.spec.js › Scope 1 — Login & temel gezinme › Dashboard açılır + sidebar/profil çalışır | desktop | ✅ passed | 4.3s |
| 2 | desktop › 01-auth-nav.spec.js › Scope 1 — Login & temel gezinme › Yanlış şifre — login fail davranışı | desktop | ✅ passed | 4.6s |
| 3 | desktop › 01-auth-nav.spec.js › Scope 1 — Login & temel gezinme › Session refresh — sayfa yenileme sonrası oturum korunur | desktop | ✅ passed | 3.9s |
| 4 | desktop › 02-dashboard-health.spec.js › Scope 2 — Dashboard + System Health › Dashboard kartları + ana modüller | desktop | ✅ passed | 6.1s |
| 5 | desktop › 02-dashboard-health.spec.js › Scope 2 — Dashboard + System Health › System Health pilot section + endpointleri | desktop | ✅ passed | 5.7s |
| 6 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › Bearer YOK ile kritik endpointlere erişim 401/403 dönmeli | desktop | ✅ passed | 0.1s |
| 7 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › URL üzerinden başka tenant verisine erişim — sahte ID ile | desktop | ✅ passed | 10.2s |
| 8 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › Console secret leak heuristik — token/password görünmez | desktop | ✅ passed | 5.2s |
