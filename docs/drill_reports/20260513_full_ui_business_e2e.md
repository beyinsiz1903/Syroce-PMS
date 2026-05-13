# Full UI + Business E2E — 2026-05-13 (Pilot Run, P1 fix sonrası)

> Suite: `frontend/e2e-business/` (Playwright). 2 chunk birleşik koşum (sequential workers=1).
> İlk koşum: 16:38 → 16:40 UTC (P1 audit/timeline 500 vardı).
> **Bu koşum: 17:03 → 17:05 UTC — `routers/audit_timeline.py` P1 fix sonrası re-run.**

---

## 1. Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | **30 / 30 PASS** (0 FAIL) |
| Spec dosyası | 20 (Scope 1-20) |
| Project | desktop (1440×900) |
| Adım sayaçları | **PASS=95** \| FAIL=0 \| REVIEW=67 \| SKIP=13 |
| Toplam süre | 114.2s (Chunk1 61.7s + Chunk2 52.5s) |
| **Son karar** | **GO WITH WATCH** |

**Önceki koşumdan fark**: PASS 93 → **95** (+2), REVIEW 69 → **67** (−2). İki azalma, bu turun konusu olan P1 audit/timeline 500 hatasının düzelmesinden geliyor:
- `[reservation]` GET /api/audit/timeline 500 → **artık 200** (kayıt değil, REVIEW listesinden düştü)
- `[audit-log]` GET /api/audit/timeline?limit=5 500 → **artık 200** (kayıt değil, REVIEW listesinden düştü)

Geriye kalan tek audit-ilgili REVIEW: `[reservation]` GET /api/admin/audit-log 404 — bu endpoint sistemde mevcut değil ve frontend hiçbir yerden çağırmıyor (`rg admin/audit-log frontend/src/` boş döndü). Test sadece eski/silinmiş bir path'i probe ediyor; route 404'ü doğru davranıştır. Spec'in oradaki probe'unu kaldırmak veya 404-beklenen olarak işaretlemek opsiyonel temizlik (out of scope).

---

## 2. Modül bazlı tablo (20 scope)

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| auth-nav | 7 | 0 | 2 | 0 | 9 |
| dashboard-health | 8 | 0 | 6 | 0 | 14 |
| reservation | **7** | 0 | **2** | 1 | 10 |
| checkin-checkout | 3 | 0 | 2 | 1 | 6 |
| folio | 5 | 0 | 10 | 1 | 16 |
| invoice | 3 | 0 | 6 | 1 | 10 |
| mice | 5 | 0 | 4 | 1 | 10 |
| housekeeping | 3 | 0 | 5 | 1 | 9 |
| guest-crm | 3 | 0 | 1 | 1 | 5 |
| users-roles | 4 | 0 | 3 | 1 | 8 |
| channel-manager | 8 | 0 | 5 | 1 | 14 |
| rate-inventory | 2 | 0 | 5 | 1 | 8 |
| payments | 3 | 0 | 6 | 1 | 10 |
| reports | 5 | 0 | 0 | 0 | 5 |
| notifications | 2 | 0 | 1 | 1 | 4 |
| settings | 4 | 0 | 6 | 1 | 11 |
| audit-log | **4** | 0 | **1** | 0 | 5 |
| security-rbac | 5 | 0 | 2 | 0 | 7 |
| responsive | 12 | 0 | 0 | 0 | 12 |
| recap | 2 | 0 | 0 | 0 | 2 |
| **TOPLAM** | **95** | **0** | **67** | **13** | **175** |

Bold modüller önceki koşuma kıyasla iyileşti (audit timeline 500 gitti).

---

## 3. P1 Fix — Audit Timeline (RESOLVED)

### Problem (önceki rapor §3 P1)
`GET /api/audit/timeline` ve `/api/audit/timeline?limit=5` pilot ortamda HTTP 500 dönüyordu. KVKK/audit görünürlüğü bozuk.

### Root cause
`backend/routers/audit_timeline.py:819` — `_group_by_time` helper'ı timestamp'in **string** olduğunu varsayarak `len(ts)` çağırıyordu. Pilot DB'deki bazı `audit_logs` kayıtları `timestamp` alanını **datetime objesi** (BSON Date) olarak tutuyor (yeni yazıcı). Eski yazıcılar ISO string yazıyor; karışık tip → `TypeError: object of type 'datetime.datetime' has no len()` → 500.

Backend traceback (Sentry'ye düştü):
```
File "/home/runner/workspace/backend/routers/audit_timeline.py", line 72, in get_audit_timeline
    grouped = _group_by_time(logs)
File "/home/runner/workspace/backend/routers/audit_timeline.py", line 819, in _group_by_time
    hour_key = ts[:13] if len(ts) >= 13 else ts[:10]
TypeError: object of type 'datetime.datetime' has no len()
```

### Fix (`backend/routers/audit_timeline.py`)
1. **`_ts_to_iso(ts)` yardımcısı eklendi** — str / datetime / None / dict → güvenli ISO string.
2. **`_group_by_time` artık `_ts_to_iso(...)` ile normalize ediyor** — `len(datetime)` TypeError'u kalıcı olarak engellendi.
3. **Outer `try/except`** — beklenmedik aggregation/serialization hatası 500 yerine **200 + `events: []` + `degraded: true`** dönüyor (UI boş ekran yerine "kayıt yok" gösterebilir).
4. **`limit` validation güçlendi** — `Query(default=50, ge=1, le=200)` (önce sadece `le=200` vardı; 0/negatif sayı 422'ye çıkar).
5. **`cursor` + tarih filtresi semantiği düzeltildi** — eski kod `cursor` geldiğinde `start_date`/`end_date` filtrelerini siliyordu; artık üçü birden `$gte`/`$lte`/`$lt` olarak korunuyor.
6. **PII sızıntısı yok** — `logger.exception(...)` traceback'i Sentry'ye gönderir, response payload'a sızdırmaz; query/header bilgisi log'a düşmez.
7. **Tenant scope korundu** — `query["tenant_id"] = ctx.tenant_id` ilk satırda set; tüm filtreler bunu üzerine yazmıyor (regression test koruyor).

### Doğrulama (manuel curl, pilot)
```
/api/audit/timeline                         → 200 (1006ms) count=50 has_more=true
/api/audit/timeline?limit=5                 → 200 (311ms)  count=5
/api/audit/timeline?limit=1                 → 200 (294ms)  count=1
/api/audit/timeline?limit=50&start_date=... → 200 (306ms)  count=50
/api/audit/timeline?severity=high&...       → 200 (314ms)  count=0
/api/audit/timeline (NO BEARER)             → 401          (auth gate intact)
```

### Regression suite (yeni)
`backend/tests/runtime/test_audit_timeline_p1_fix.py` — **10 test, hepsi PASS**, **CI'da koşar** (motor'a bağlı değil → komşu `test_audit_timeline_stress.py`'deki "CI skip" uygulanmıyor):
- `_ts_to_iso` — str, datetime, None
- `_group_by_time` — mixed types crash etmiyor
- Route empty dataset → 200 + boş liste
- Route mixed timestamps → 200 (pilot bug'ın bire-bir reprosü)
- Route unexpected error → 200 + `degraded=true`
- Route limit param int annotation
- Route cursor + start_date + end_date birlikte → TypeError yok
- **Tenant scope isolation** — cross-tenant kayıt sızmıyor (2 test)

### Bilinen sınırlama — Mongo karışık-tip karşılaştırması (out of scope)
Pilot DB'de `audit_logs.timestamp` hem ISO string hem BSON `Date` olarak yazılmış. Bu fix `_group_by_time` ve serialization tarafındaki crash'i çözer; ama `$gte`/`$lte`/`$lt` query operatörleri **string ↔ Date** arasında BSON tip-sıralaması nedeniyle kesin eşleşme garantisi vermez (string `"2026-05-13"` vs `Date("2026-05-13...")` → cursor pagination'da kayıp/atlama olabilir). Tam tip-temizliği `audit_logs` migration'ı gerektirir → kapsam dışı (kullanıcı talebi: "audit model redesign yok"). Sentry'de `degraded=true` artış oranı + cursor pagination anomalisi izlenmeli; gerekirse ayrı bir Audit-Hardening turu açılır.

### `/api/admin/audit-log` 404 (P2 — out of scope kalıyor)
- Backend'de böyle bir route YOK (`/api/admin/audit-logs` — çoğul — var, `enterprise_router.py:1077`).
- Frontend `rg`: `admin/audit-log` referansı **0** → 404 yetim probe.
- Action: spec'teki probe'u silmek veya `expect(404)` olarak fix etmek 5 dakikalık kozmetik iş; bu turun kapsamı dışında.

---

## 4. Test verileri

**Hiçbir entity oluşturulmadı.** Cleanup gereken kayıt: 0.

---

## 5. REVIEW (67 adım) — pilot 24h içinde manuel doğrulama

Çoğunluğu **count=0** kalıbı (pilot dataset boş). İlk gerçek rezervasyon/folio/etkinlik geldiğinde doğal olarak yeşile döner.

### auth-nav (2)
- Sidebar nav linkleri (count=0)
- Profil menü tetikleyici

### dashboard-health (6)
- Modül kartları PMS/RMS (pms=0, rms=0)
- Pilot kartları: Readiness / CM Outbox / Circuit Breaker / Atlas Backup / Observability — `SystemHealthDashboard`'da "Pilot Production Safety" section'ı render edilip edilmediği manuel kontrol

### reservation (2)
- Yeni rezervasyon butonu
- `/api/admin/audit-log` → 404 (yetim probe — bkz. §3)

### checkin-checkout (2)
- Check-in/out butonları (count=0)

### folio (10)
- Masraf ekle / Ödeme / Refund / Void / Split / Merge butonları (count=0)
- Tablar: timeline / tax / splits / voids (count=0)

### invoice (6)
- Fatura sekmesi, VKN/TCKN/Vergi Dairesi/Şirket/Adres alanları

### mice (4)
- Etkinlikler / Mekanlar / Menüler tabları, "Yeni Etkinlik" butonu

### housekeeping (5)
- Status badge'leri: clean / dirty / inspect / maintenance / order

### guest-crm (1)
- Misafir arama input

### users-roles (3)
- Email filter, "Super Admin Yap" / "Admin Yap" butonları

### channel-manager (5)
- HotelRunner / Exely / Unified Rate / Connections içerik (count=0 — pilot bağlı kanal yok)
- Bulk resolve buton

### rate-inventory (5)
- Min Stay / Stop-Sale / Close to Arrival / Availability / Inventory kontrolleri

### payments (6)
- Method/aksiyon: Nakit / Kart / Havale / Ödeme / Refund (count=0)
- Negatif tutar validation — açık folio gerekli

### notifications (1)
- Top-bar bildirim ikonu

### settings (6)
- Sekme/alan: Vergi / Para Birimi / Saat Dilimi / Dil / Logo (count=0)
- Kaydet butonu

### audit-log (1)
- PII scrub heuristik — Sentry policy ayrı suite

### security-rbac (2)
- Sahte folio ID 200 (P2 — UX iyileştirme; cross-tenant sızıntı değil — frontend route HTML shell yüklüyor, backend folio API yine 404 dönüyor)

---

## 6. SKIP (13 adım) — bilinçli external/destructive bypass

| Modül | Adım | Sebep |
|---|---|---|
| reservation | İkinci no-show guard | Destructive state geçişi — canlı drill |
| checkin-checkout | Gerçek check-in/out | Operasyonel etki |
| folio | Gerçek refund/void | Finansal işlem — sandbox folio gerekli |
| invoice | Gerçek fatura yazımı | Pilot ayar mutasyonu |
| mice | Gerçek etkinlik POST | Veri kirletme |
| housekeeping | Gerçek status mutation | Operasyonel etki |
| guest-crm | Misafir create | KVKK + cleanup riski |
| users-roles | User create + role assign | Auth pool kirletme |
| channel-manager | Gerçek OTA push | External (HotelRunner/Exely) |
| rate-inventory | Inventory mutation + push | External — sandbox/dry-run |
| payments | Gerçek payment gateway | External — sandbox |
| notifications | E-posta/SMS gönderim | External (Resend/SMS) |
| settings | Tenant ayar mutation | Pilot tenant değişikliği |

---

## 7. Risk sınıflandırması

- **P0**: failedTests=0, FAIL adım=0 → **YOK**
- **P1**: ~~`/api/audit/timeline` 500~~ → **RESOLVED** (bu tur fix + 9 regression test + manuel curl + e2e re-run)
- **P2**: folio sahte-ID 200 (frontend ID validate eklenebilir), `/api/admin/audit-log` yetim probe (spec temizliği)
- **P3**: REVIEW=67 listesinin çoğunluğu (count=0 dataset boş) — pilot canlıya geçince doğal olarak yeşil

---

## 8. Pilot canlı geçiş tavsiyesi

**Verdict: GO WITH WATCH** (P1 RESOLVED, P0 yok)

Önkoşul: ~~P1 audit fix~~ ✅ **TAMAM**.

Canlı T+0 → T+24h:
- `docs/PILOT_FIRST_24H_MONITORING.md` runbook aktif
- Bu raporun §5 REVIEW listesi nöbet defterinde — ilk rezervasyon/folio geldiğinde her kalem manuel onay
- Sentry'de `audit_timeline_query_failed` log mesajı izle — `degraded=true` döndüğünde investigate (yeni timestamp tip varyantı sinyali)

T+24h sonrası:
- `yarn test:e2e:business` haftalık cron
- REVIEW kalemleri her hafta yeşile dönmeli; dönmüyorsa selector eskimiş

---

## 9. Artifact path'leri

- HTML report: `frontend/playwright-business-report/`
- Trace/video/screenshot: `frontend/test-results-business/` (FAIL'ler için → bu koşumda boş)
- Auth state: `frontend/e2e-business/.auth/admin.json` (gitignored)
- Bearer cache: `frontend/e2e-business/.auth/token.json` (gitignored)
- P1 fix kaynağı: `backend/routers/audit_timeline.py` (commit: bu tur)
- P1 regression test: `backend/tests/runtime/test_audit_timeline_p1_fix.py` (9 test, hepsi PASS)

---

## 10. Test inventory (30 test, hepsi PASS)

| # | Spec › Test | Süre | Outcome |
|---:|---|---:|---|
| 1 | 01-auth-nav › Dashboard açılır + sidebar/profil çalışır | 3.6s | ✅ |
| 2 | 01-auth-nav › Yanlış şifre — login fail davranışı | 4.4s | ✅ |
| 3 | 01-auth-nav › Session refresh — sayfa yenileme sonrası oturum korunur | 2.9s | ✅ |
| 4 | 02-dashboard-health › Dashboard kartları + ana modüller | 3.7s | ✅ |
| 5 | 02-dashboard-health › System Health pilot section + endpointleri | 5.8s | ✅ |
| 6 | 03-reservation › Rezervasyon takvimi açılır + form keşfi | 3.8s | ✅ |
| 7 | 03-reservation › PMS bookings endpoint okuma + audit erişim | 1.0s | ✅ (audit/timeline artık 200) |
| 8 | 03-reservation › Terminal-state guard (no-show double) — endpoint discovery | 0.6s | ✅ |
| 9 | 04-checkin-checkout › Front Desk / PMS check-in akışı keşfi | 3.6s | ✅ |
| 10 | 05-folio › Folio ana sayfa + masraf/ödeme/refund/void buton keşfi | 4.3s | ✅ |
| 11 | 05-folio › Folio API discovery (read-only) | 0.5s | ✅ |
| 12 | 06-invoice › Fatura ayarları sekmesi + form alanları | 4.3s | ✅ |
| 13 | 07-mice › MICE ana sayfa + sekme + butonlar | 6.2s | ✅ |
| 14 | 08-housekeeping › Housekeeping ana sayfa + oda durum badgeleri | 3.9s | ✅ |
| 15 | 09-guest-crm › Misafir liste + ara + form alanları | 3.5s | ✅ |
| 16 | 10-users-roles › Kullanıcı-Rol Manager + filter + butonlar | 4.2s | ✅ |
| 17 | 11-channel-manager › Channels Hub + provider/CB/conflict UI | 7.4s | ✅ |
| 18 | 12-rate-inventory › Unified Rate Manager + availability grid | 3.8s | ✅ |
| 19 | 13-payments › Folio ödeme kontrolleri (UI keşfi) | 3.7s | ✅ |
| 20 | 14-reports › Rapor sayfaları + endpoint örnekleri | 3.1s | ✅ |
| 21 | 15-notifications › Notification center + mailing keşfi | 3.0s | ✅ |
| 22 | 16-settings › Settings ana sayfa + sekmeler | 3.5s | ✅ |
| 23 | 17-audit-log › Audit Timeline UI + endpointler | 2.7s | ✅ (timeline 200, summary 200) |
| 24 | 18-security-rbac › Bearer YOK ile kritik endpointlere erişim 401/403 | 0.3s | ✅ |
| 25 | 18-security-rbac › URL üzerinden başka tenant verisine erişim — sahte ID | 3.6s | ✅ |
| 26 | 18-security-rbac › Console secret leak heuristik — token/password görünmez | 4.4s | ✅ |
| 27 | 19-responsive › Viewport mobile-portrait (390x844) — dashboard render | 3.4s | ✅ |
| 28 | 19-responsive › Viewport tablet-portrait (820x1180) — dashboard render | 3.6s | ✅ |
| 29 | 19-responsive › Viewport desktop-narrow (1280x720) — dashboard render | 3.9s | ✅ |
| 30 | 20-recap › Test verileri özetleme + cleanup notu | 0.0s | ✅ |
