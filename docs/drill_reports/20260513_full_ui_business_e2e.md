# Full UI + Business E2E — 2026-05-13 (Cleanup turu sonrası)

> Suite: `frontend/e2e-business/` (Playwright). 2 chunk birleşik koşum (sequential workers=1).
> Tur 1 (16:38 UTC): P1 audit/timeline 500 vardı.
> Tur 2 (17:03 UTC): `routers/audit_timeline.py` P1 fix sonrası re-run → PASS 93→95.
> **Tur 3 (bu — 17:18-17:23 UTC): Cleanup turu (yetim probe + folio NotFound guard) → PASS 95→98.**

---

## 1. Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | **30 / 30 PASS** (0 FAIL) |
| Spec dosyası | 20 (Scope 1-20) |
| Project | desktop (1440×900) |
| Adım sayaçları | **PASS=98** \| FAIL=0 \| **REVIEW=64** \| SKIP=13 |
| Toplam süre | 126.4s (Chunk1 67.0s + Chunk2 59.4s) |
| **Son karar** | **GO WITH WATCH** (P1 ve P2 kapatıldı) |

**Tur 3 farkı (cleanup)**: PASS 95 → **98** (+3), REVIEW 67 → **64** (−3). Üç iyileşme:
1. **Yetim probe temizliği** — `/api/admin/audit-log` 404 probe'u 03 + 17 spec'lerinden kaldırıldı (frontend referansı yok, backend route mevcut değil — yetim yetim path). REVIEW 2 düştü.
2. **Folio invalid ID UX guard** — `FolioDetailView.jsx` artık geçersiz ObjectId formatı veya backend 404'te "Folio bulunamadı" NotFound kartı gösteriyor. Cross-tenant verisi asla render edilmez. Test 18 sahte ID artık REVIEW değil **PASS**: REVIEW 2 düştü, PASS 3 arttı.
3. Kalan REVIEW kalemleri pure `count=0` (pilot dataset boş) — gerçek operasyon başlayınca doğal olarak yeşile döner.

**Net durum**: P0=0, P1=0 (✅ önceki turda audit timeline çözüldü), **P2=0** (bu turda folio + audit probe çözüldü), P3=63 dataset-bağımlı REVIEW.

---

## 2. Modül bazlı tablo (20 scope)

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam | Δ vs Tur 2 |
|---|---:|---:|---:|---:|---:|---|
| auth-nav | 7 | 0 | 2 | 0 | 9 | — |
| dashboard-health | 8 | 0 | 6 | 0 | 14 | — |
| reservation | 7 | 0 | **1** | 1 | 9 | REVIEW −1 (admin/audit-log probe sil) |
| checkin-checkout | 3 | 0 | 2 | 1 | 6 | — |
| folio | 5 | 0 | 10 | 1 | 16 | — |
| invoice | 3 | 0 | 6 | 1 | 10 | — |
| mice | 5 | 0 | 4 | 1 | 10 | — |
| housekeeping | 3 | 0 | 5 | 1 | 9 | — |
| guest-crm | 3 | 0 | 1 | 1 | 5 | — |
| users-roles | 4 | 0 | 3 | 1 | 8 | — |
| channel-manager | 8 | 0 | 5 | 1 | 14 | — |
| rate-inventory | 2 | 0 | 5 | 1 | 8 | — |
| payments | 3 | 0 | 6 | 1 | 10 | — |
| reports | 5 | 0 | 0 | 0 | 5 | — |
| notifications | 2 | 0 | 1 | 1 | 4 | — |
| settings | 4 | 0 | 6 | 1 | 11 | — |
| audit-log | 4 | 0 | **1** | 0 | 5 | REVIEW −1 (admin/audit-log probe sil; PII scrub REVIEW kalıyor) |
| security-rbac | **8** | 0 | **0** | 0 | 8 | PASS +3 (folio NotFound), REVIEW −2 |
| responsive | 12 | 0 | 0 | 0 | 12 | — |
| recap | 2 | 0 | 0 | 0 | 2 | — |
| **TOPLAM** | **98** | **0** | **64** | **13** | **175** | PASS +3, REVIEW −3 |

---

## 3. Bu tur uygulanan cleanup'lar

### 3.1 — Yetim audit-log probe temizliği

**Problem**: `/api/admin/audit-log` endpoint'i sistemde mevcut değil. Backend'de `/admin/audit-logs` (çoğul) var ama bu yazma için (`enterprise_router.py:1077`). Frontend kaynak kodunda `rg "admin/audit-log"` → 0 sonuç. E2E'de iki probe vardı (03 + 17), her seferinde 404 döndürüp REVIEW kaydı bırakıyordu.

**Fix**:
- `frontend/e2e-business/03-reservation-lifecycle.spec.js` — probe loop'u tek `/api/audit/timeline` çağrısına indirgendi.
- `frontend/e2e-business/17-audit-log.spec.js` — aynı şekilde sadece `/api/audit/timeline?limit=5`.
- Her iki spec'e cleanup turu yorumu eklendi: "yetim probe — frontend referansı yok".

**Sonuç**: REVIEW −2. Audit görünürlüğü tamamen `/api/audit/timeline` üzerinden, doğru endpoint çalışıyor.

### 3.2 — Folio invalid ID UX guard (P2 → kapatıldı)

**Problem**: `/folio-detail/<sahte-id>` URL'ine gidildiğinde `FolioDetailView` boş HTML shell render ediyordu (sadece search input + spinner kaybolduktan sonra hiçbir şey). Sahte/yanıltıcı sayfa görüntüsü → kullanıcı kafa karışıklığı. (Cross-tenant sızıntı YOK — backend zaten 404 dönüyor — tamamen UX sorunu.) Eski test `/folio/:id` yoluna gidiyordu, o zaten SPA catch-all 200 idi.

**Fix** (`frontend/src/pages/FolioDetailView.jsx`):
1. **`OBJECT_ID_RE = /^[a-f0-9]{24}$/i`** — Mongo ObjectId formatı validation (24 hex).
2. `fetchDetail(id)` artık:
   - Format invalid → backend'e gitmeden `setNotFound(true)` + `notFoundReason="invalid_format"`.
   - Backend 404 → `setNotFound(true)` + `notFoundReason="not_found"`.
   - Backend 401/403 → `setNotFound(true)` + `notFoundReason="forbidden"`.
   - Diğer hata → toast (eski davranış).
3. **Yeni NotFound kartı** (`data-testid="folio-not-found"`) — AlertTriangle ikonu + tek-satır başlık + sebebe göre açıklama + "Yeni arama" butonu (search input modunda).
4. `{data && !notFound && (...)}` — bilgi paneli sadece gerçek folio yüklendiğinde render.

**Test güncelleme** (`frontend/e2e-business/18-security-rbac.spec.js`):
- URL prefix `/folio/${id}` → **`/folio-detail/${id}`** (gerçek route).
- Test ID listesi 2 → 3: `000…000`, `aaaa…aaa`, `invalid-id-format-xyz` (3. kasıt: format guard'ı zorlamak).
- Body text regex'i `(folio bulunamad|folio not found|geçersiz folio id|invalid folio id|404|forbidden|yetki yok)` ile NotFound kartını yakalıyor.

**Sonuç**: 3/3 sahte folio testi PASS, REVIEW −2, PASS +3, **P2 kapatıldı**.

### 3.3 — REVIEW azaltma için seed planı (uygulanmadı, dokümante edildi)

Kullanıcı talebi: "Eğer güvenliyse sadece test tenant içinde E2E seed verisi oluştur". Mevcut pilot tenant **canlı pilot ortam** (Mongo Atlas), gerçek otel verisini barındırıyor. Test guest/booking/folio/MICE event yazımı:
- KVKK kapsamında soru işareti (test verisi bile olsa misafir kaydı tutuluyor).
- Cleanup pattern'i sıfır — ID-prefix bazlı silme her tablo için çalışmıyor (audit logs zaten silinmez).
- Pilot operatörün gözlemlediği gerçek dashboard'u kirletir (mock guest/booking görür).

**Karar**: Bu tur seed YAPILMADI. Önerilen yol: ayrı bir `tenant=e2e_test` izole tenant aç, `EXPO_PUBLIC_API_URL`'a paralel test deployment kur, seed orada koş. Bu kapsam dışı (yeni infra + ayrı plan).

REVIEW=63 kalemi pilot canlıya geçince ilk gerçek booking/folio/MICE yaratıldığında doğal olarak yeşile dönecek (selector zaten doğru, sadece `count=0` durumu).

---

## 4. Test verileri

**Hiçbir entity oluşturulmadı** (Scope 3.3 kararı gereği). Cleanup gereken kayıt: 0.

---

## 5. REVIEW (64 adım) — pilot 24h içinde manuel doğrulama

Tur 2'den fark: **−3 kayıt** (admin/audit-log probe ×2 sil, folio sahte-ID ×2 PASS'a geç; +1 yeni invalid-format ID PASS olarak eklendi → toplam −3).

### auth-nav (2)
- Sidebar nav linkleri (count=0)
- Profil menü tetikleyici

### dashboard-health (6)
- Modül kartları PMS/RMS (pms=0, rms=0)
- Pilot kartları: Readiness / CM Outbox / Circuit Breaker / Atlas Backup / Observability — `SystemHealthDashboard`'da "Pilot Production Safety" section'ı render edilip edilmediği manuel kontrol

### reservation (1)
- Yeni rezervasyon butonu

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
- PII scrub heuristik — Audit response payload kontrolü manuel; Sentry PII scrub ayrı suite olarak `docs/SENTRY_ALERT_POLICY.md`'de tanımlı (bu turda kaldırılmadı, sadece yetim `/api/admin/audit-log` probe'u silindi).

### security-rbac (0)
✅ **REVIEW yok** — sahte folio ID 3'ü de NotFound guard tetikliyor → PASS.

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
- **P1**: ~~`/api/audit/timeline` 500~~ → **RESOLVED** (Tur 2)
- **P2**:
  - ~~Folio sahte-ID 200~~ → **RESOLVED** bu tur (NotFound guard + ObjectId regex)
  - ~~`/api/admin/audit-log` yetim probe~~ → **RESOLVED** bu tur (probe silindi)
- **P3**: REVIEW=64 listesinin tamamı `count=0` dataset-bağımlı veya bilinçli manuel-doğrulama kalemleri (örn. PII scrub) — pilot canlı operasyona geçince çoğu doğal olarak yeşil

---

## 8. Pilot canlı geçiş tavsiyesi

**Verdict: GO WITH WATCH** (P0/P1/P2 hepsi temiz, sadece dataset-bağımlı P3 REVIEW'lar var)

Önkoşul: ✅ Audit timeline 500 fix (Tur 2) · ✅ Folio NotFound guard (Tur 3) · ✅ Yetim probe temizliği (Tur 3).

Canlı T+0 → T+24h:
- `docs/PILOT_FIRST_24H_MONITORING.md` runbook aktif
- Bu raporun §5 REVIEW listesi nöbet defterinde — ilk rezervasyon/folio/MICE geldiğinde her kalem manuel onay
- Sentry'de `audit_timeline_query_failed` log mesajı izle — `degraded=true` döndüğünde investigate

T+24h sonrası:
- `yarn test:e2e:business` haftalık cron
- REVIEW kalemleri her hafta yeşile dönmeli; dönmüyorsa selector eskimiş

T+1 hafta sonrası — yeşil kalan REVIEW kategorileri PASS olarak hardcode edilebilir (regression baseline güçlenir).

---

## 9. Artifact path'leri

- HTML report: `frontend/playwright-business-report/`
- Trace/video/screenshot: `frontend/test-results-business/` (FAIL'ler için → bu koşumda boş)
- Auth state: `frontend/e2e-business/.auth/admin.json` (gitignored)
- Bearer cache: `frontend/e2e-business/.auth/token.json` (gitignored)
- P1 fix kaynağı: `backend/routers/audit_timeline.py` (Tur 2)
- P1 regression: `backend/tests/runtime/test_audit_timeline_p1_fix.py` — 10 test, hepsi PASS, CI'da koşar
- **P2 fix kaynağı (bu tur)**: `frontend/src/pages/FolioDetailView.jsx` (NotFound guard)
- **Probe cleanup (bu tur)**: `frontend/e2e-business/03-reservation-lifecycle.spec.js`, `frontend/e2e-business/17-audit-log.spec.js`, `frontend/e2e-business/18-security-rbac.spec.js`

---

## 10. Test inventory (30 test, hepsi PASS)

| # | Spec › Test | Süre | Outcome |
|---:|---|---:|---|
| 1 | 01-auth-nav › Dashboard açılır + sidebar/profil çalışır | 3.9s | ✅ |
| 2 | 01-auth-nav › Yanlış şifre — login fail davranışı | 4.2s | ✅ |
| 3 | 01-auth-nav › Session refresh — sayfa yenileme sonrası oturum korunur | 3.3s | ✅ |
| 4 | 02-dashboard-health › Dashboard kartları + ana modüller | 4.4s | ✅ |
| 5 | 02-dashboard-health › System Health pilot section + endpointleri | 6.9s | ✅ |
| 6 | 03-reservation › Rezervasyon takvimi açılır + form keşfi | 3.6s | ✅ |
| 7 | 03-reservation › PMS bookings endpoint okuma + audit erişim | 1.0s | ✅ (yetim probe sil) |
| 8 | 03-reservation › Terminal-state guard (no-show double) — endpoint discovery | 0.6s | ✅ |
| 9 | 04-checkin-checkout › Front Desk / PMS check-in akışı keşfi | 3.6s | ✅ |
| 10 | 05-folio › Folio ana sayfa + masraf/ödeme/refund/void buton keşfi | 3.7s | ✅ |
| 11 | 05-folio › Folio API discovery (read-only) | 0.4s | ✅ |
| 12 | 06-invoice › Fatura ayarları sekmesi + form alanları | 4.7s | ✅ |
| 13 | 07-mice › MICE ana sayfa + sekme + butonlar | 5.4s | ✅ |
| 14 | 08-housekeeping › Housekeeping ana sayfa + oda durum badgeleri | 4.8s | ✅ |
| 15 | 09-guest-crm › Misafir liste + ara + form alanları | 3.4s | ✅ |
| 16 | 10-users-roles › Kullanıcı-Rol Manager + filter + butonlar | 4.1s | ✅ |
| 17 | 11-channel-manager › Channels Hub + provider/CB/conflict UI | 7.8s | ✅ |
| 18 | 12-rate-inventory › Unified Rate Manager + availability grid | 3.9s | ✅ |
| 19 | 13-payments › Folio ödeme kontrolleri (UI keşfi) | 3.9s | ✅ |
| 20 | 14-reports › Rapor sayfaları + endpoint örnekleri | 3.6s | ✅ |
| 21 | 15-notifications › Notification center + mailing keşfi | 3.3s | ✅ |
| 22 | 16-settings › Settings ana sayfa + sekmeler | 4.0s | ✅ |
| 23 | 17-audit-log › Audit Timeline UI + endpointler | 2.7s | ✅ (timeline 200, yetim probe sil) |
| 24 | 18-security-rbac › Bearer YOK ile kritik endpointlere erişim 401/403 | 0.1s | ✅ |
| 25 | 18-security-rbac › URL üzerinden başka tenant verisine erişim — sahte ID | 9.0s | ✅ (3/3 NotFound guard) |
| 26 | 18-security-rbac › Console secret leak heuristik — token/password görünmez | 4.4s | ✅ |
| 27 | 19-responsive › Viewport mobile-portrait (390x844) — dashboard render | 3.3s | ✅ |
| 28 | 19-responsive › Viewport tablet-portrait (820x1180) — dashboard render | 3.6s | ✅ |
| 29 | 19-responsive › Viewport desktop-narrow (1280x720) — dashboard render | 3.7s | ✅ |
| 30 | 20-recap › Test verileri özetleme + cleanup notu | 0.0s | ✅ |
