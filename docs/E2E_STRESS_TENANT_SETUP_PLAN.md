# 500 Oda Stress Test — İzole Tenant Kurulum Planı

> Hedef: 500 odalı %100 dolu tesis stress E2E suite'i için **gerçek pilot/canlı tenant'ı kirletmeyen** izole bir test ortamı kurmak.
> Bu doküman: ön-koşullar, gereken env/secret listesi, tenant provisioning adımları, bulk seed extension'ı, dış servis dry-run gate'leri ve "ready to run" kabul kriterleri.
> Bu plan onaylandıktan sonra ayrı bir tur'da: (a) suite scaffolding (`frontend/e2e-stress/`), (b) bulk seed factory genişletme, (c) ilk koşum + rapor.

---

## 1. Neden ayrı tenant şart?

Pilot tenant şu an **canlı** (Atlas cluster, gerçek otel verisi). Stress brief'in 9. kuralı:
> "Test tenant değilse NO-GO ver ve destructive adımları çalıştırma."

Pilot üzerinde 500 oda + 500 booking + 500 folio + room move + housekeeping mutation + MICE event + complaint + bulk OTA simulation koşmak:
- KVKK ihlali (500 sahte misafir kaydı + ID/iletişim alanları)
- Cleanup pattern eksik (audit_logs ve bazı outbox kayıtları silinmez)
- Pilot operatörünün gözlemlediği gerçek dashboard'ı kirletir
- Atlas 500-koleksiyon limiti (digitalocean.md gotcha) yakın — extra tenant koleksiyonları ile aşılabilir
- Gerçek Sentry alert'leri test verisinden tetiklenir → on-call kirlenmesi

**Çözüm**: Aşağıdaki üç deployment paterninden birini seç ve ayrı tenant_id'li, izole MongoDB/Redis ile çalıştır.

---

## 2. Üç deployment paterni (öneri sırasıyla)

### Pattern A — Aynı Atlas cluster + ayrı tenant_id (en hızlı, ~2 saat)
- **Cluster**: Mevcut `MONGO_ATLAS_URI` (pilot cluster).
- **Tenant**: Yeni `tenant_id` (örn. `e2e_stress_500`) `POST /api/admin/tenants` endpoint ile yarat.
- **İzolasyon kaynağı**: `TenantScopedCollection` (backend/core/tenant_db.py:48) — tüm `find/insert/update` query'lerine otomatik `{tenant_id: ...}` enjekte ediyor. **STRICT_TENANT_MODE=true** aktif olmalı (cross-tenant erişim TenantViolationError fırlatır).
- **Risk**: Yanlışlıkla `tenant_id` filtresi olmayan bir admin route varsa (audit ve bazı `system_db` koleksiyonları), pilot ve stress verisi karışabilir. Pre-flight: `rg "system_db\|get_collection\b" backend/` ile tenant-aware olmayan query'ler taranmalı.
- **Atlas tier**: `ATLAS_TIER` env zaten var. M10+ önerilir (500 oda + 500 booking + 1000+ folio item için 2-3 GB working set).
- **Cleanup**: Tenant-scoped koleksiyonlar `delete_many({tenant_id: "e2e_stress_500"})` ile temizlenir. Audit_logs sadece arşivlenir (silinmez — KVKK için sıkıntı yok çünkü fake data).

### Pattern B — Ayrı Atlas cluster (orta, ~4 saat)
- Yeni Mongo Atlas project (free M0 yeterli değil, M10+ gerekli).
- Ayrı `MONGO_ATLAS_URI_STRESS` secret.
- Tamamen fiziksel izolasyon. Pilot'a sıfır risk.
- Maliyet: Atlas M10 ~$60/ay.

### Pattern C — Local MongoDB DigitalOcean'te (en izole, ~1 saat ama persistence yok)
- `backend/start.sh` zaten local Mongo başlatıyor.
- `MONGO_ATLAS_URI` boş bırakılırsa fallback local'a düşer mi? — `backend/core/database.py` kontrol edilmeli. Eğer hard-coded Atlas ise küçük patch lazım.
- DigitalOcean container yeniden başlayınca veri uçar → bir koşum için tek yeterli.
- DigitalOcean Reserved VM gerekli (storage persistence). Maliyet: $7/ay.

**Tavsiye**: **Pattern A** + ayrı stress tenant_id ile başla. Pre-flight tenant-leak audit'i yap (3-4 saat). Sorun çıkarsa B'ye geç.

---

## 3. Gerekli env / secret listesi (DigitalOcean Secrets)

### Mevcut (yeniden kullanılacak)
- `MONGO_ATLAS_URI` — Pattern A için aynı; Pattern B için `MONGO_ATLAS_URI_STRESS` ayrıca lazım.
- `JWT_SECRET` — aynı (admin login için).
- `RESEND_API_KEY`, `RESEND_FROM` — koşumda **kullanılmayacak** ama `EXTERNAL_DRY_RUN=true` ile bypass edilecek.
- `VITE_SENTRY_DSN` — stress run'da `SENTRY_ENVIRONMENT=stress` olmalı (alert routing ayrı kanala).
- `ATLAS_TIER` — M10+ olarak güncellenmeli (eğer pilot M0/M2 ise).

### Yeni eklenmesi gerekenler
| Secret | Değer | Amaç |
|---|---|---|
| `E2E_STRESS_TENANT_ID` | `e2e_stress_500` | Stress suite'in hedefleyeceği izole tenant |
| `E2E_STRESS_TENANT_NAME` | `E2E Stress 500-Room Hotel` | UI'da görünür ad |
| `E2E_STRESS_ADMIN_EMAIL` | `stress-admin@e2e.local` | Stress tenant admin kullanıcı |
| `E2E_STRESS_ADMIN_PASSWORD` | (güçlü random) | Login |
| `E2E_ALLOW_DESTRUCTIVE_STRESS` | `true` | Brief gate #3 — eksikse suite NO-GO + read-only düşer |
| `E2E_EXTERNAL_DRY_RUN` | `true` | Brief gate #4 — payment/OTA/SMS/email/KVKK gerçek çağrı yok |
| `E2E_ROOM_COUNT` | `500` | Bulk seed boyutu |
| `E2E_OCCUPANCY_RATE` | `1.0` | Active stay yüzdesi |
| `STRICT_TENANT_MODE` | `true` | Cross-tenant erişimi TenantViolationError ile reddet |
| `SENTRY_ENVIRONMENT` | `stress` | Alert routing ayrı (pilot on-call'u kirletme) |
| `ENABLE_SETUP_ENDPOINTS` | `1` (sadece stress kurulum sırasında) | Stress tenant + ilk admin user yaratmak için |
| `SETUP_SECRET` | (güçlü random) | Setup endpoint koruması |
| `ROOM_QR_SECRET` | (güçlü random) | QR guest request bölümü için (zaten missing_secrets'te) |
| `PUBLIC_APP_URL` | `https://${CLOUD_DEV_DOMAIN}` | QR ve mail link'leri için (zaten missing) |

### Dış servis dry-run gate'leri (suite içinde okunacak)
| Gate Env | Default | Davranış |
|---|---|---|
| `E2E_PAYMENT_SANDBOX_REQUIRED` | `true` | Gerçek payment gateway URL tespit edilirse SKIP |
| `E2E_OTA_DRY_RUN_REQUIRED` | `true` | HotelRunner/Exely production credential varsa SKIP |
| `E2E_SMS_MOCK_REQUIRED` | `true` | SMS provider env varsa SKIP |
| `E2E_EMAIL_MOCK_REQUIRED` | `true` | RESEND_API_KEY varsa, suite ya `RESEND_API_KEY=mock` ile koşar ya SKIP |
| `E2E_KVKK_MOCK_REQUIRED` | `true` | Quick-ID demo mode (ENABLE_QUICKID_DEMO=1) zorunlu |

---

## 4. Bulk seed extension (mevcut → 500 oda)

### Mevcut durum (`backend/seed/`)
- `rooms.py` — sabit room_configs listesi (~25-120 oda toplam, 6 oda tipi).
- `guests.py` — 50 misafir.
- `bookings.py` — geçmiş/aktif/gelecek karışımı, ~tahmin 30-50 booking.
- `DemoDataGenerator` (`backend/demo_data_generator.py`) — auto_seed.py boş DB'de çalıştırıyor.

### Genişletme ihtiyacı (`backend/seed/stress/` yeni dizin)
| Dosya | Üretim hedefi | Strateji |
|---|---|---|
| `stress/rooms_500.py` | 500 oda, 20 oda tipi, 10 kat, 5 blok | Parametric loop: bloklar A-E, katlar 1-10, oda numaraları 101-150 |
| `stress/guests_500.py` | 500 misafir + 50 VIP/late-co/allergy/accessibility flag | `E2E_STRESS_<ts>_guest_<i>` prefix; sahte TC: 11111111110-11111111610 (validation bypass için test serisi) |
| `stress/bookings_500.py` | 500 active stay (bugün checkin, +1-7 gün checkout) | `E2E_STRESS_<ts>_book_<i>` prefix; `room_night_locks` doğru oluşturulmalı |
| `stress/folios_500.py` | 500 folio + 1000 charge + 200 payment | Vergi/KDV/konaklama vergisi hesaplı |
| `stress/rate_plans_10.py` | 10 rate plan + 5 channel | Hardcoded |
| `stress/cleanup.py` | Tüm `E2E_STRESS_<ts>_` prefix kayıtlarını sil | `delete_many({_id: {$regex: "^E2E_STRESS_"}})` her koleksiyonda |

### Performans hedefi
- Tüm 500 oda + booking + folio seed batch'i: < 60 saniye
- Pre-allocate batch insert (Motor `insert_many` 100'lük chunk)
- `room_night_locks` unique compound index'i öncesi valide et (`db.room_night_locks.create_index([("tenant_id",1),("room_id",1),("date",1)], unique=True)`)

### Seed API endpoint (yeni)
`POST /api/admin/stress/seed` (super_admin only, `ENABLE_SETUP_ENDPOINTS=1` gate'li):
```json
{
  "tenant_id": "e2e_stress_500",
  "room_count": 500,
  "occupancy_rate": 1.0,
  "data_prefix": "E2E_STRESS_20260513T180000_"
}
```
Response: `{seeded: {rooms: 500, guests: 500, bookings: 500, folios: 500, charges: 1000}, duration_ms: 47000}`

`POST /api/admin/stress/cleanup` — prefix-bazlı temizlik. Audit_logs hariç tüm scoped koleksiyonlardan silmeli.

---

## 5. Dış servis dry-run gate'leri (suite koşumunda)

### Brief'in 1-13 ön kapısı + bizim eklediklerimiz
| # | Gate | Doğrulama yöntemi |
|---|---|---|
| 1 | Login başarılı | `POST /api/auth/login` 200 + token |
| 2 | Tenant test/staging | `GET /api/admin/tenants/me` → `tenant_id == E2E_STRESS_TENANT_ID` ve `name` regex `/e2e[\s\-_]stress/i` |
| 3 | E2E_ALLOW_DESTRUCTIVE_STRESS=true | Suite global setup'ta env oku |
| 4 | E2E_EXTERNAL_DRY_RUN=true | Aynı |
| 5 | Payment gateway sandbox | Backend'de `payment_provider.mode == "sandbox"` health endpoint'i |
| 6 | OTA dry-run | `GET /api/channels/health` her connector `mode == "sandbox"` veya `dry_run == true` |
| 7 | Email/SMS mock | `RESEND_API_KEY` env değeri `mock-` prefix'li veya `DISABLE_EMAIL=1` |
| 8 | KVKK mock | `GET /api/quickid/health` → `demo_mode: true` (`ENABLE_QUICKID_DEMO=1`) |
| 9 | Backup readiness | `GET /api/admin/backup/readiness` → status `ready` |
| 10 | System health REVIEW+ | `GET /api/admin/system/health` → overall not `failed` |
| 11 | Sentry environment | `process.env.SENTRY_ENVIRONMENT in ['stress','staging']` (production değil) |
| 12 | Outbox backlog kabul edilebilir | `GET /api/channels/outbox/stats` → `pending < 100` |
| 13 | Circuit breaker initial state recorded | `GET /api/channels/circuit-breaker/status` snapshot suite başlangıcında dosyaya yazılır |

### Gate fail davranışı
Herhangi biri fail → suite **NO-GO + read-only mode**:
- 11 bölümün her birinde `if (!gates.passed) { test.skip(true, "Stress gate fail"); return; }`
- Sadece `GET` keşif çağrıları çalışır
- Rapor: "GATE-FAIL-NO-GO" verdict

---

## 6. Pre-flight tenant-leak audit (Pattern A için zorunlu)

Aynı Atlas cluster'da pilot ve stress tenant birlikte yaşayacaksa, kod tabanında **tenant_id filtresi olmayan query** YOK olmalı. Audit script'i:

```bash
# 1. Tüm DB query'lerini bul
rg "\.find\(|\.find_one\(|\.update_one\(|\.update_many\(|\.delete_many\(|\.aggregate\(" \
   backend/ --type=py | grep -v __pycache__ > /tmp/_db_queries.txt

# 2. tenant_id içermeyenleri filtrele
grep -v "tenant_id" /tmp/_db_queries.txt > /tmp/_tenant_leaks.txt

# 3. Manuel review — `system_db`/`get_system_db` kullanımı OK (cross-tenant by design),
#    `get_db()` veya proxy üzerinden olanlar OK (auto-inject), kalanlar incelenmeli.
wc -l /tmp/_tenant_leaks.txt
```

Beklenti: < 20 satır, hepsi `system_db` / `get_collection` (tenant-by-design global) olmalı. Kalan herhangi bir scoped query → blocker P0.

---

## 7. Test suite scaffold (sonraki tur)

Plan onaylandıktan sonra üretilecek:

### `frontend/e2e-stress/`
```
playwright.stress.config.js       # ayrı outputDir, ayrı reporter, fail-fast=false
fixtures/
  gates.js                        # Bölüm 0 — 13 ön-kapı kontrolü
  stress-auth.js                  # storageState login (E2E_STRESS_ADMIN_*)
  stress-data-factory.js          # E2E_STRESS_<ts>_ prefix factory
  cleanup-registry.js             # afterAll'da cleanup tetikle
  observers.js                    # console + network capture
  perf.js                         # 95p latency aggregation
specs/
  00-gates.spec.js                # Bölüm 0 — koşmadan önce hepsi PASS olmalı
  01-bulk-seed-500.spec.js        # Bölüm 1 — 500 oda + booking + folio yarat, count'ları doğrula
  02-day-turnover.spec.js         # Bölüm 2 — 100 C/O + 100 C/I + 50 turnover + no-show + cancel + walk-in
  03-room-move.spec.js            # Bölüm 3 — 50 room move + race conditions
  04-folio-mass.spec.js           # Bölüm 4 — 100 charge + payment + 25 split + 25 merge + closed-folio guard
  05-invoice.spec.js              # Bölüm 5 — 50 bireysel + 20 şirket fatura + VKN/TCKN validation
  06-qr-requests.spec.js          # Bölüm 6 — 100 QR session + 150 request (HK/teknik/RS/şikayet)
  07-complaints.spec.js           # Bölüm 7 — 30 şikayet lifecycle
  08-housekeeping-mass.spec.js    # Bölüm 8 — 500 oda HK status flow
  09-mice-events.spec.js          # Bölüm 9 — 20 etkinlik + çakışma + folio/invoice
  10-reports-perf.spec.js         # Bölüm 10 — 10 rapor + tarih filter + export + perf eşikleri
  11-cm-stress.spec.js            # Bölüm 11 — sandbox: 50 cancel + 20 no-show + overbooking + CB OPEN
markdown-reporter.mjs             # Konsolide rapor üretici
```

### Reporter rapor formatı
`docs/drill_reports/YYYYMMDD_500room_full_operational_stress.md`:
1. Yönetici özeti + GO/GO-WITH-WATCH/NO-GO
2. Gate sonuçları tablosu (13 kalem)
3. Bölüm bazlı PASS/FAIL/REVIEW/SKIP sayaçları (11 bölüm)
4. P0/P1/P2/P3 risk sınıflandırması
5. Performans eşik tablosu (dashboard < 3s, 500-room list < 5s, raporlar < 10s, 95p API)
6. Test data inventory (yaratılan + cleanup edilen + cleanup edilemeyen)
7. Cleanup yapılamayan kayıtlar tablosu (audit_logs prefix listesi)
8. Cross-tenant isolation doğrulaması
9. Sentry alert sayıları (stress env'de)
10. Outbox/circuit breaker before/after snapshot

---

## 8. "Ready to run" kabul kriterleri

Aşağıdaki 10 madde tek tek ✅ olduğunda stress suite tetiklenebilir:

1. ✅ Pattern A/B/C kararı verildi ve cluster hazır
2. ✅ Yeni 14 secret DigitalOcean'e eklendi (Bölüm 3)
3. ✅ `e2e_stress_500` tenant `POST /api/admin/tenants` ile yaratıldı + ilk admin login doğrulandı
4. ✅ `STRICT_TENANT_MODE=true` aktif, restart sonrası backend up
5. ✅ Pre-flight tenant-leak audit (Bölüm 6) çalıştı, kalan leak yok
6. ✅ Bulk seed API (`POST /api/admin/stress/seed`) implement edildi ve smoke koşumu geçti (10 oda)
7. ✅ Cleanup API (`POST /api/admin/stress/cleanup`) implement edildi ve smoke geçti
8. ✅ Suite scaffold (`frontend/e2e-stress/`) komite (Bölüm 7)
9. ✅ Sentry'de `stress` environment kanalı tanımlı, alert routing ayrı
10. ✅ İletişim: pilot operatörü stress koşumunun pilot dashboard'unu etkilemeyeceği konusunda bilgilendirildi (cross-tenant isolation garantisi)

---

## 9. Tahmini iş yükü ve sıra

| Faz | İş | Süre | Çıktı |
|---|---|---:|---|
| **F1** | Pattern A/B/C kararı + Atlas tier upgrade (gerekirse) | 30 dk | Karar dokümanı |
| **F2** | 14 secret hazırlama + DigitalOcean'e ekleme | 30 dk | Secrets aktif |
| **F3** | Stress tenant create + admin user + STRICT_TENANT_MODE on | 45 dk | Login çalışıyor |
| **F4** | Pre-flight tenant-leak audit + bulgu fix | 2-3 saat | Audit raporu, temiz |
| **F5** | Bulk seed/cleanup endpoint + 10-oda smoke | 2-3 saat | API hazır |
| **F6** | Stress seed extension (rooms_500, guests_500, bookings_500, folios_500) | 3-4 saat | 500-oda seed çalışıyor |
| **F7** | Suite scaffold + 00-gates.spec + 01-bulk-seed.spec | 2-3 saat | İlk 2 spec PASS |
| **F8** | Bölüm 2-11 spec implementation (paralel subagent ile bölünebilir) | 8-12 saat | 11 spec hazır |
| **F9** | İlk full koşum + rapor üretimi | 1-2 saat | Konsolide rapor |
| **F10** | Bulgu triyaj + iyileştirme + ikinci koşum | değişken | Final rapor + verdict |
| **TOPLAM** | — | **~22-30 saat** | Stress suite production-ready |

---

## 10. Out of scope (bu plan kapsamında YAPILMAYANLAR)

- Stress tenant production'a deploy edilmeyecek (sadece dev/staging)
- Pilot tenant'a hiçbir mutasyon yapılmayacak
- Gerçek payment/OTA/SMS/email/KVKK çağrısı yapılmayacak (her zaman dry-run)
- 500-oda performans hedefleri SLA değil — gözlem amaçlı (sadece rapora yazılır)
- Distributed load testing (k6/JMeter) bu plana dahil değil — bu plan tek-worker fonksiyonel stress
- Atlas tier upgrade maliyeti onayı kullanıcının kararı (M10 ~$60/ay)

---

## 11. Karar noktaları (kullanıcıdan beklenen)

1. **Pattern seçimi**: A (aynı cluster + STRICT mode), B (ayrı cluster, $60/ay), C (local DigitalOcean, persistence yok) — hangisi?
2. **Atlas tier**: Pattern A için mevcut tier 500-oda working set'e yeterli mi? Upgrade gerekli mi?
3. **Sentry**: `stress` environment için ayrı project/key mi yoksa mevcut DSN tag-based ayrım mı?
4. **F4 pre-flight audit**: Tenant-leak bulgu çıkarsa fix bu turun parçası mı yoksa ayrı tur mu?
5. **Sıra**: F1-F3 tamamlanıp tek tur'da mı başlıyoruz, yoksa F1-F6 birleştirip "infra hazır" milestone'una sonra mı geçiyoruz?

Karar verildiğinde **F1'den başlayan ayrı bir tur** açılır; bu plan dokümante eden referans olarak kalır.
