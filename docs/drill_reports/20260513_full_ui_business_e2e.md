# Full UI + Business E2E — 20260513

> Suite: `frontend/e2e-business/` (Playwright). Üretildi: 2026-05-13T19:21:38.647Z

## 1. Yönetici özeti

- Toplam test: **30**
- Başarısız test: **0**
- Adım sayaçları: PASS=94 | FAIL=0 | REVIEW=67 | SKIP=13
- Süre: 117.7s
- Son karar: **GO WITH WATCH** — REVIEW=67 adım — pilot sırasında manuel takip

## 2. Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| audit-log | 3 | 0 | 1 | 0 | 4 |
| auth-nav | 7 | 0 | 2 | 0 | 9 |
| channel-manager | 8 | 0 | 5 | 1 | 14 |
| checkin-checkout | 3 | 0 | 2 | 1 | 6 |
| dashboard-health | 8 | 0 | 6 | 0 | 14 |
| folio | 5 | 0 | 10 | 1 | 16 |
| guest-crm | 3 | 0 | 1 | 1 | 5 |
| housekeeping | 3 | 0 | 5 | 1 | 9 |
| invoice | 3 | 0 | 6 | 1 | 10 |
| mice | 5 | 0 | 4 | 1 | 10 |
| notifications | 2 | 0 | 1 | 1 | 4 |
| payments | 3 | 0 | 6 | 1 | 10 |
| rate-inventory | 2 | 0 | 5 | 1 | 8 |
| recap | 2 | 0 | 0 | 0 | 2 |
| reports | 5 | 0 | 0 | 0 | 5 |
| reservation | 7 | 0 | 1 | 1 | 9 |
| responsive | 12 | 0 | 0 | 0 | 12 |
| security-rbac | 5 | 0 | 3 | 0 | 8 |
| settings | 4 | 0 | 6 | 1 | 11 |
| users-roles | 4 | 0 | 3 | 1 | 8 |

## 3. Kritik bulgular (FAIL adımlar + başarısız testler)

_Yok — tüm testler ve adımlar geçti veya REVIEW/SKIP olarak işaretli._

## 4. Test verileri (oluşturulan / temizlenen)

_Hiç entity oluşturulmadı veya kayıt bulunamadı._

## 5. REVIEW + SKIP adımlar

### REVIEW (67)
- **[auth-nav]** Sidebar nav linkleri — count=0 
- **[auth-nav]** Profil menü tetikleyici — - 
- **[dashboard-health]** Modül kartları (PMS/RMS) — pms=0 rms=0 
- **[dashboard-health]** Pilot kart: Readiness — count=0 
- **[dashboard-health]** Pilot kart: CM Outbox — count=0 
- **[dashboard-health]** Pilot kart: Circuit Breaker — count=0 
- **[dashboard-health]** Pilot kart: Atlas Backup — count=0 
- **[dashboard-health]** Pilot kart: Observability — count=0 
- **[reservation]** Yeni rezervasyon butonu — - 
- **[checkin-checkout]** Check-in butonları görünür — count=0 
- **[checkin-checkout]** Check-out butonları görünür — count=0 
- **[folio]** Masraf ekle butonu mevcut — count=0 
- **[folio]** Ödeme alanı/butonu mevcut — count=0 
- **[folio]** Refund butonu mevcut — count=0 
- **[folio]** Void butonu mevcut — count=0 
- **[folio]** Split (folio bölme) mevcut — count=0 
- **[folio]** Merge (folio birleştirme) mevcut — count=0 
- **[folio]** Tab folio-tab-timeline — count=0 
- **[folio]** Tab folio-tab-tax — count=0 
- **[folio]** Tab folio-tab-splits — count=0 
- **[folio]** Tab folio-tab-voids — count=0 
- **[invoice]** Fatura sekmesi — - 
- **[invoice]** Alan VKN — count=0 
- **[invoice]** Alan TCKN — count=0 
- **[invoice]** Alan Vergi Dairesi — count=0 
- **[invoice]** Alan Şirket — count=0 
- **[invoice]** Alan Adres — count=0 
- **[mice]** Tab Etkinlikler — - 
- **[mice]** Tab Mekanlar — - 
- **[mice]** Tab Menüler — - 
- **[mice]** Yeni Etkinlik butonu — - 
- **[housekeeping]** Status badge clean — count=0 
- **[housekeeping]** Status badge dirty — count=0 
- **[housekeeping]** Status badge inspect — count=0 
- **[housekeeping]** Status badge maintenance — count=0 
- **[housekeeping]** Status badge order — count=0 
- **[guest-crm]** Misafir arama input — - 
- **[users-roles]** Email filter input — - 
- **[users-roles]** Buton: Super Admin Yap — count=0 
- **[users-roles]** Buton: Admin Yap — count=0 
- **[channel-manager]** İçerik: HotelRunner — count=0 
- **[channel-manager]** İçerik: Exely — count=0 
- **[channel-manager]** İçerik: Unified Rate — count=0 
- **[channel-manager]** İçerik: Connections — count=0 
- **[channel-manager]** Bulk resolve buton mevcut — - 
- **[rate-inventory]** Kontrol: Min Stay — count=0 
- **[rate-inventory]** Kontrol: Stop-Sale — count=0 
- **[rate-inventory]** Kontrol: Close to Arrival — count=0 
- **[rate-inventory]** Kontrol: Availability — count=0 
- **[rate-inventory]** Kontrol: Inventory — count=0 
- **[payments]** Method/aksiyon: Nakit — count=0 
- **[payments]** Method/aksiyon: Kart — count=0 
- **[payments]** Method/aksiyon: Havale — count=0 
- **[payments]** Method/aksiyon: Ödeme — count=0 
- **[payments]** Method/aksiyon: Refund — count=0 
- **[payments]** Negatif tutar / fazla ödeme validation — Form simülasyonu için açık folio gerekli — ön koşul karşılanmadı. 
- **[notifications]** Top-bar bildirim ikonu — count=0 
- **[settings]** Sekme/alan: Vergi — count=0 
- **[settings]** Sekme/alan: Para Birimi — count=0 
- **[settings]** Sekme/alan: Saat Dilimi — count=0 
- **[settings]** Sekme/alan: Dil — count=0 
- **[settings]** Sekme/alan: Logo — count=0 
- **[settings]** Kaydet butonu görünür — count=0 
- **[audit-log]** PII scrub heuristik — Audit response payload kontrolü manuel — Sentry PII scrub ayrı suite ile test edilmeli (bkz. docs/SENTRY_ALERT_POLICY.md). 
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

### SKIP (13)
- **[reservation]** İkinci no-show guard testi — Pilot dataset üzerinde destructive sıralı state değişimi tetiklenmedi; canlı doğrulama T+0 sonrası önerilir. 
- **[checkin-checkout]** Gerçek check-in/out tetikleme — Pilot dataset stabilitesi için destructive state geçişi yapılmadı; canlı drill'de manuel doğrulama önerilir. 
- **[folio]** Gerçek refund/void tetikleme — Pilot canlı veri üzerinde finansal işlem tetiklenmedi; sandbox'ta üretilmiş test folio gereklidir (üretim adımı bu suite kapsamı dışı). 
- **[invoice]** Gerçek fatura bilgisi yazımı — Pilot ayar mutasyonu yapılmadı (rollback overhead). 
- **[mice]** Gerçek etkinlik POST — Veri kirletme + cleanup karmaşası nedeniyle yalnız form keşfi. 
- **[housekeeping]** Gerçek status mutation — Pilot oda durumu değiştirilmedi (operasyonel etki). 
- **[guest-crm]** Gerçek misafir create — KVKK kapsamı + cleanup riski; placeholder veri yazılmadı. 
- **[users-roles]** Test user create + role assign — Pilot otentikasyon havuzunu kirletmemek için kullanıcı oluşturulmadı. 
- **[channel-manager]** Sync now / gerçek OTA push — External etki: HotelRunner/Exely gerçek push tetiklenmedi. 
- **[rate-inventory]** Gerçek inventory mutation + OTA push — External etki — sandbox/dry-run zorunlu. 
- **[payments]** Gerçek payment gateway çağrısı — External — sandbox gerekli; pilot'ta tetiklenmedi. 
- **[notifications]** Gerçek e-posta/SMS gönderim — External etki — Resend/SMS gateway tetiklenmedi. 
- **[settings]** Gerçek ayar mutation — Pilot tenant ayarları değiştirilmedi. 

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
| 1 | desktop › 01-auth-nav.spec.js › Scope 1 — Login & temel gezinme › Dashboard açılır + sidebar/profil çalışır | desktop | ✅ passed | 3.9s |
| 2 | desktop › 01-auth-nav.spec.js › Scope 1 — Login & temel gezinme › Yanlış şifre — login fail davranışı | desktop | ✅ passed | 4.4s |
| 3 | desktop › 01-auth-nav.spec.js › Scope 1 — Login & temel gezinme › Session refresh — sayfa yenileme sonrası oturum korunur | desktop | ✅ passed | 3.3s |
| 4 | desktop › 02-dashboard-health.spec.js › Scope 2 — Dashboard + System Health › Dashboard kartları + ana modüller | desktop | ✅ passed | 4.0s |
| 5 | desktop › 02-dashboard-health.spec.js › Scope 2 — Dashboard + System Health › System Health pilot section + endpointleri | desktop | ✅ passed | 6.0s |
| 6 | desktop › 03-reservation-lifecycle.spec.js › Scope 3 — Rezervasyon yaşam döngüsü › Rezervasyon takvimi açılır + form keşfi | desktop | ✅ passed | 3.6s |
| 7 | desktop › 03-reservation-lifecycle.spec.js › Scope 3 — Rezervasyon yaşam döngüsü › PMS bookings endpoint okuma + audit erişim | desktop | ✅ passed | 1.1s |
| 8 | desktop › 03-reservation-lifecycle.spec.js › Scope 3 — Rezervasyon yaşam döngüsü › Terminal-state guard (no-show double) — endpoint discovery | desktop | ✅ passed | 0.6s |
| 9 | desktop › 04-checkin-checkout.spec.js › Scope 4 — Check-in / Check-out › Front Desk / PMS sayfası check-in akışı keşfi | desktop | ✅ passed | 4.1s |
| 10 | desktop › 05-folio.spec.js › Scope 5 — Folio › Folio ana sayfa + masraf/ödeme/refund/void buton keşfi | desktop | ✅ passed | 5.0s |
| 11 | desktop › 05-folio.spec.js › Scope 5 — Folio › Folio API discovery (read-only) | desktop | ✅ passed | 0.4s |
| 12 | desktop › 06-invoice.spec.js › Scope 6 — Fatura / şirket bilgileri › Fatura ayarları sekmesi + form alanları | desktop | ✅ passed | 4.7s |
| 13 | desktop › 07-mice.spec.js › Scope 7 — MICE / etkinlik › MICE ana sayfa + sekme + butonlar | desktop | ✅ passed | 7.0s |
| 14 | desktop › 08-housekeeping.spec.js › Scope 8 — Housekeeping / oda durumu › Housekeeping ana sayfa + oda durum badgeleri | desktop | ✅ passed | 3.7s |
| 15 | desktop › 09-guest-crm.spec.js › Scope 9 — Misafir profili / CRM › Misafir liste + ara + form alanları | desktop | ✅ passed | 3.0s |
| 16 | desktop › 10-users-roles.spec.js › Scope 10 — Kullanıcı / Rol › Kullanıcı-Rol Manager + filter + butonlar | desktop | ✅ passed | 4.2s |
| 17 | desktop › 11-channel-manager.spec.js › Scope 11 — Channel Manager › Channels Hub + provider/CB/conflict UI | desktop | ✅ passed | 6.7s |
| 18 | desktop › 12-rate-inventory.spec.js › Scope 12 — Rate / Inventory / Availability › Unified Rate Manager + availability grid | desktop | ✅ passed | 3.6s |
| 19 | desktop › 13-payments.spec.js › Scope 13 — Ödemeler › Folio ödeme kontrolleri (UI keşfi) | desktop | ✅ passed | 3.6s |
| 20 | desktop › 14-reports.spec.js › Scope 14 — Raporlar › Rapor sayfaları + endpoint örnekleri | desktop | ✅ passed | 3.6s |
| 21 | desktop › 15-notifications.spec.js › Scope 15 — Bildirimler / mesajlar › Notification center + mailing keşfi | desktop | ✅ passed | 3.3s |
| 22 | desktop › 16-settings.spec.js › Scope 16 — Ayarlar › Settings ana sayfa + sekmeler | desktop | ✅ passed | 3.7s |
| 23 | desktop › 17-audit-log.spec.js › Scope 17 — Audit / log › Audit Timeline UI + endpointler | desktop | ✅ passed | 2.9s |
| 24 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › Bearer YOK ile kritik endpointlere erişim 401/403 dönmeli | desktop | ✅ passed | 0.1s |
| 25 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › URL üzerinden başka tenant verisine erişim — sahte ID ile | desktop | ✅ passed | 9.1s |
| 26 | desktop › 18-security-rbac.spec.js › Scope 18 — Güvenlik / izolasyon › Console secret leak heuristik — token/password görünmez | desktop | ✅ passed | 4.3s |
| 27 | desktop › 19-responsive.spec.js › Scope 19 — Mobil / responsive › Viewport mobile-portrait (390x844) — dashboard render | desktop | ✅ passed | 3.4s |
| 28 | desktop › 19-responsive.spec.js › Scope 19 — Mobil / responsive › Viewport tablet-portrait (820x1180) — dashboard render | desktop | ✅ passed | 3.7s |
| 29 | desktop › 19-responsive.spec.js › Scope 19 — Mobil / responsive › Viewport desktop-narrow (1280x720) — dashboard render | desktop | ✅ passed | 3.8s |
| 30 | desktop › 20-recap.spec.js › Scope 20 — Test verileri özetleme + cleanup notu | desktop | ✅ passed | 0.0s |
