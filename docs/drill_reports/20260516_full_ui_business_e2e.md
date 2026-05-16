# Full UI + Business E2E — 20260516

> Suite: `frontend/e2e-business/` (Playwright). Üretildi: 2026-05-16T09:23:47.039Z

## 1. Yönetici özeti

- Toplam test: **4**
- Başarısız test: **0**
- Adım sayaçları: PASS=12 | FAIL=0 | REVIEW=9 | SKIP=1
- Süre: 26.5s
- Son karar: **GO WITH WATCH** — REVIEW=9 adım — pilot sırasında manuel takip

## 2. Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| channel-manager | 7 | 0 | 6 | 1 | 14 |
| security-rbac | 5 | 0 | 3 | 0 | 8 |

## 3. Kritik bulgular (FAIL adımlar + başarısız testler)

_Yok — tüm testler ve adımlar geçti veya REVIEW/SKIP olarak işaretli._

## 4. Test verileri (oluşturulan / temizlenen)

_Hiç entity oluşturulmadı veya kayıt bulunamadı._

## 5. REVIEW + SKIP adımlar

### REVIEW (9)
- **[channel-manager]** İçerik: HotelRunner — count=0 
- **[channel-manager]** İçerik: Exely — count=0 
- **[channel-manager]** İçerik: Unified Rate — count=0 
- **[channel-manager]** İçerik: Connections — count=0 
- **[channel-manager]** Conflict resolve butonları — rows=0 resolveBtns=0 
- **[channel-manager]** Bulk resolve buton mevcut — - 
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

### SKIP (1)
- **[channel-manager]** Sync now / gerçek OTA push — External etki: HotelRunner/Exely gerçek push tetiklenmedi. 

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
| 1 | desktop › 11-channel-manager.spec.js › Scope 11 — Channel Manager › Channels Hub + provider/CB/conflict UI | desktop | ✅ passed | 6.8s |
| 2 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › Bearer YOK ile kritik endpointlere erişim 401/403 dönmeli | desktop | ✅ passed | 0.1s |
| 3 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › URL üzerinden başka tenant verisine erişim — sahte ID ile | desktop | ✅ passed | 9.0s |
| 4 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › Console secret leak heuristik — token/password görünmez | desktop | ✅ passed | 4.8s |
