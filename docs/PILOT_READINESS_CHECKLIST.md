# Pilot Readiness Checklist — Syroce PMS

**Tur**: Discovery (kod yazılmadı, sadece envanter + sınıflandırma)
**Tarih**: 11 Mayıs 2026
**Branch baseline**: `main @ 7029e3c7` (cross-tenant E2E v4 dahil)
**Hedef**: Belirli bir pilot otel için go-live öncesi son kontrol listesi

> Pilot otel kimliği bu dokümana eklenmedi (`[PILOT_TENANT_ID]` placeholder); hotel_id, property_profile, channel manager hesapları ve admin email’i kullanıcı tarafından doldurulacak.

---

## Yönetici Özeti

| Kategori | Toplam Bulgu | BLOCKER | HIGH | MEDIUM/LOW |
|---|---:|---:|---:|---:|
| 1. Backup / Rollback | 6 | 1 | 1 | 4 |
| 2. CI Green Run | 5 | 1 | 2 | 2 |
| 3. Staging Deploy Smoke | 5 | 1 | 2 | 2 |
| 4. Tenant Isolation Smoke (post-v4) | 16 yüzey | 0* | 7 | 9 |
| 5. Channel Manager Reconciliation | 4 başlık | 3 | 0 | 1 |
| 6. Seed / Demo Data | 4 | 0 | 1 | 3 |
| 7. Known Gaps | ~9 marker + 6 gotcha | 3 | 3 | birden fazla |
| 8. Operasyonel Gözlemlenebilirlik | 5 | 0 | 2 | 3 |

\* v4 ile finansal/yetki/PII yüzeyi ana hatları kapatıldı; kalan 16 yüzeyin **hiçbiri tek başına BLOCKER değil** ama 7’si HIGH — pilot öncesi v5 testine girmesi şiddetle önerilir.

**Net pilot kararı (öneri)**:
- **GO** — eğer aşağıdaki **3 hard-blocker** kapatılırsa: (a) `EXELY_IP_WHITELIST` üretim secret’ı, (b) frontend Vitest CI gate’e girer, (c) Tenant-bazlı restore prosedürü dokümante + bir kez drill yapılır.
- **NO-GO** — bu üçünden biri eksikse.

Diğer HIGH bulgular pilot başlamadan önce takvime alınmalı, ama pilot’u bloklamaz.

---

## 1. Backup / Rollback

### Mevcut durum
- **Backup script**: `backend/scripts/backup_daily.sh` — `mongodump --gzip`, tüm DB scope (`--db="${DB_NAME}"`).
- **Doküman**: `docs/procedures/BACKUP_AND_RESTORE.md` (günlük 02:00, haftalık), `docs/procedures/DISASTER_RECOVERY.md`.
- **Restore drill prosedürü**: `BACKUP_AND_RESTORE.md:660` — aylık manuel test tarif edilmiş; **geçmiş drill kaydı yok**.
- **Code-level rollback**: `backend/core/feature_flags.py:41` — `kill_switch`, `tenant_overrides`, `rollout_percentage` destekleyen tam mekanizma. ✅
- **Atlas snapshot otomasyonu**: yok (Atlas’ın native snapshot policy’sine güveniliyor, doğrulanmadı).

### Bulgular
- **BLOCKER — Tenant-bazlı restore prosedürü yok**: `mongodump` tüm DB’yi yedekliyor, ama bir pilot otelin verisini yanlışlıkla bozarsanız 39 başka tenant’ı etkilemeden geri alacak yol dokümante değil. Pilot başlamadan önce **tek tenant restore drill’i** (boş bir staging’de) bir kez koşulmalı ve `docs/procedures/` altına `TENANT_RESTORE_DRILL.md` eklenmeli.
- **HIGH — Atlas snapshot policy doğrulanmamış**: Atlas console’da bu cluster için snapshot frequency + retention bilinmiyor; pilot öncesi 1 saatlik kontrol.
- **MEDIUM — Restore drill kaydı yok**: Aylık drill prosedürü tanımlı ama hiç koşulmamış (CHANGELOG/playbooks’ta iz yok).
- **LOW — Feature flag kapsamı**: `kill_switch` mevcut; pilot otele özel hangi modüllerin “sadece bu tenant için kapat” diye işaretlenebileceği listelenmemiş.

### Sahibi: DevOps
### Pilot-blocker mı: **Evet (1 madde)**

---

## 2. CI Green Run

### Mevcut durum
- **CI**: `.github/workflows/ci-cd.yml` — `backend-test` ve `load-test` Hard Gate (satır 106, 209).
- **Backend test envanteri**: **300 test dosyası** (`backend/tests/`). `_quarantine/` dizini flake izolasyonu için kullanılıyor.
- **E2E suite (kritik)**: 7 dosya
  - `test_e2e_reservation_flow.py` (Apr)
  - `test_overbooking_prevention_e2e.py` (Apr)
  - `test_id_photo_admin_e2e.py` (May)
  - `test_reservation_lifecycle_e2e.py` (May 11) — v1
  - `test_reservation_noshow_e2e.py` (May 11) — v2
  - `test_folio_charge_payment_e2e.py` (May 11) — v3
  - `test_cross_tenant_isolation_e2e.py` (May 11) — v4 ✅
- **Frontend**: 13 test dosyası (`frontend/src/**/__tests__`).
- **Mobile**: ayrı workflow `mobile-smoke.yml`.
- **CI test scope**: tüm 300 değil, `ci-cd.yml:174` içinde **curated liste** (Hardening, Resilience, Battle, Crypto…) çalıştırılıyor.
- **Frontend CI**: sadece ESLint koşuluyor (`ci-cd.yml:100`); **Vitest CI gate dışında**.
- **Skip/xfail**: `_quarantine/` + birkaç dosyada `pytest.skip` (test_b2b_webhooks 8 adet, battle/sprint2 11 adet).

### Bulgular
- **BLOCKER — Frontend Vitest CI’da gate değil**: 13 test dosyası mevcut ama PR’ları durdurmuyor. Pilot kullanıcılarının dokunduğu UI’da regresyon CI’da yakalanmıyor. **`frontend-quality.yml` veya `ci-cd.yml`’ye `yarn vitest run` ekle**.
- **HIGH — Backend curated CI yetersiz**: 300 test var, CI’da yaklaşık ⅓’ü koşuyor. v1-v4 E2E’lerinin curated listede olduğunu **doğrula** (özellikle yeni v4: `test_cross_tenant_isolation_e2e.py`); değilse ekle.
- **HIGH — `_quarantine/` dizini için temizlik politikası yok**: Quarantined testler ne zaman geri döner / silinir tanımsız. Pilot öncesi listenin kısa bir sahibi olmalı.
- **MEDIUM — pytest `--timeout=30` saniye**: E2E’lerde demo tenant Atlas RTT ile 30s sıkışık olabilir; v4 yerel 30s’de geçti ama CI’da hassas.
- **LOW — Test süresi metrik yok**: CI’da total wall-clock + per-suite süreler dashboard’a düşmüyor.

### Sahibi: Platform / QA
### Pilot-blocker mı: **Evet (1 madde — frontend Vitest gate)**

---

## 3. Staging Deploy Smoke

### Mevcut durum
- **Deploy hedefi**: `.replit:105` — `deploymentTarget = "static"`, `frontend/build` yayınlanıyor.
- **Production-grade deploy**: `deploy/deploy.sh` — Docker Compose tabanlı (`deploy/docker-compose.production.yml`).
- **ENV listesi (zorunlu — `deploy/deploy.sh:71`)**: `DB_NAME`, `JWT_SECRET`, `CORS_ORIGINS`, `CM_CREDENTIAL_KEY`, `CM_MASTER_KEY_CURRENT`.
- **Health endpoint’leri**: `backend/app.py:123-138` — `/health`, `/health/live`, `/health/ready` (DB ping + boot check). ✅
- **Bootstrap**: `backend/bootstrap/phases/` (a→g) — index, seed, migration sıralı.
- **Production go-live readiness API**: `backend/routers/production_golive.py` — `/api/production-golive/readiness` skor + sağlık kontrolleri (`test_production_golive_api.py` test ediyor). ✅

### Bulgular
- **BLOCKER — Pilot-spesifik smoke runbook yok**: CI içinde inline smoke var, ama `deploy/SMOKE.md` veya `deploy/smoke.sh` (deploy sonrası 1 dakikada çalışan checklist) yok. Önerilen 6 adım: (1) `/health/ready` 200, (2) admin login, (3) `GET /api/pms/bookings` 200, (4) reservation create + cancel, (5) `/api/production-golive/readiness` skoru ≥X, (6) Sentry’de yeni `ERROR` yok.
- **HIGH — Atlas TLS sertifikalarının deploy entegrasyonu**: `deploy/deploy.sh`’de Atlas-spesifik TLS bundle adımı yok; pilot tenant için Atlas `mongodb+srv://` bağlantısının deploy environment’ta TLS doğrulamasından geçtiği test edilmedi.
- **HIGH — `userenv.shared` içinde production secret’lar plaintext**: `.replit`’te `JWT_SECRET`, `CM_MASTER_KEY_CURRENT`, `AFSADAKAT_ADMIN_TOKEN` plaintext görünüyor. Bunlar dev için OK ama pilot deployment’ı **Replit Secrets vault**’tan okuyacak şekilde sabitlenmeli — replit.md `Production Secret Management` gotcha’sı zaten uyarıyor.
- **MEDIUM — `EXELY_IP_WHITELIST` env**: `replit.md` BLOCKER olarak işaretliyor (üretimde yoksa 503). Pilot `.env`’ine eklenmeli (Channel Manager altında tekrar geçecek).
- **LOW — `CORS_ORIGINS` pilot domain’e güncellenmeli**: şu an dev domain’ler.

### Sahibi: DevOps
### Pilot-blocker mı: **Evet (1 madde — smoke runbook)**

---

## 4. Tenant Isolation Smoke (post-v4)

### v4 ile kapanan yüzeyler ✅
| Test | Yüzey |
|---|---|
| T1 | `GET /api/pms/reservations/{id}/full-detail` |
| T2 | `POST /api/pms-core/cancel` |
| T3 | `POST /api/pms-core/folio/charge` |
| T4 | `POST /api/pms-core/no-show` |
| T5 | `GET /api/pms/bookings` (list) |
| T6 | `GET /api/pms/guests/{id}` + list |

### Pilot öncesi v5 önerilen yüzeyler

| Yüzey | Endpoint | Risk | Kapsama önerisi |
|---|---|---|---|
| Folio Payment | `POST /api/frontdesk/folio/{id}/payment` | **HIGH** | v5 mutlaka |
| Folio Read | `GET /api/frontdesk/folio/{booking_id}` | MED | v5 |
| Check-in | `POST /api/frontdesk/checkin/{booking_id}` | **HIGH** | v5 mutlaka |
| Check-out | `POST /api/frontdesk/checkout/{booking_id}` | **HIGH** | v5 mutlaka |
| Kiosk check-in | `POST /api/frontdesk/kiosk-checkin` | **HIGH** | v5 (IDOR riski) |
| HK complete-task | `POST /api/housekeeping/mobile/complete-task/{id}` | MED | v5 |
| HK upload-photo | `POST /api/housekeeping/upload-photo` | MED | v5 |
| Maintenance create | `POST /api/maintenance/work-orders` | MED | v5 |
| Maintenance update | `PATCH /api/maintenance/work-orders/{id}` | MED | v5 |
| IoT room-devices | `GET /api/iot/room-devices/{room_id}` | **HIGH** | v5 (gizlilik) |
| Revenue report | `GET /api/revenue/market-segment-breakdown` | MED | v5 |
| **Night audit** | `GET /api/night-audit/financial-summary` | **HIGH** | v5 mutlaka |
| Tenant users (admin) | `GET /api/admin/tenant-users` | **HIGH** | v5 (PII) |
| Granted permissions | `PATCH /api/admin/users/{id}/granted-permissions` | **HIGH** | v5 (yetki escalation) |
| Tenant modules | `PATCH /api/admin/tenants/{id}/modules` | LOW | super_admin guard yeterli |
| Tenant subscription | `PATCH /api/admin/tenants/{id}/subscription` | LOW | super_admin guard yeterli |

### Bulgular
- v5 kapsamı ChatGPT’ye onaylatılırsa **6 mutlak HIGH** (Payment + Check-in + Check-out + Kiosk + IoT + Night Audit + tenant-users + granted-permissions = aslında 8) olarak daraltılabilir. v4 pattern aynen kullanılır → tahmini efor: 1 oturum.
- **Çoğu endpoint scoping mekanizması iki kategoride**: (a) `OperationContext` / `frontdesk_service` ctx-bazlı filter, (b) router içinde `find({"tenant_id": current_user.tenant_id, ...})` manuel filter. Her ikisi de v4’te denendi ve doğru davrandı; v5 sadece daha geniş yüzey.

### Sahibi: Backend / QA
### Pilot-blocker mı: **Hayır** — ama v5 olmadan pilot’a giderseniz finans + check-in akışında IDOR riski görünmez kalır. **Şiddetle önerilen.**

---

## 5. Channel Manager Reconciliation

### Mevcut durum
- **Exely**: `backend/domains/channel_manager/providers/exely/provider.py` — SOAP + ARI push + reservation pull (OTA_ReadRQ). Webhook: `exely_webhook_router.py:284`. IP whitelist: `:381`. XXE/SSRF koruma: `defusedxml`.
- **HotelRunner**: `backend/domains/channel_manager/providers/hotelrunner/provider.py` — REST v2. Pull retries (`manual=3`, `scheduled=2`) `retry.py`’de.
- **SXI Bus**: `backend/integrations/xchange/bus.py:158` — atomik idempotency (`uniq_tenant_msg_partner` index). SSRF guard: `backend/integrations/xchange/safety.py:253` (`safe_post_async`, DNS-rebinding safe).
- **Sandbox simulation**: `backend/channel_manager/application/sandbox_simulation/scenarios.py` — Duplicate Delivery, Delayed Ack, Retry Storm, Stale Provider State senaryoları **var**.

### Bulgular
- **BLOCKER — `EXELY_IP_WHITELIST` env**: replit.md’de explicit BLOCKER. Pilot otelin Exely instance’ının source IP’leri öğrenilip env’e yazılmalı, yoksa 503.
- **BLOCKER — “Stop-sale push” + “No-show sync” reconciliation senaryosu sandbox’ta yok**: Akışlar unit test seviyesinde var (v2 no-show E2E) ama provider sandbox simulation’ında smoke senaryosu olarak yok. Pilot’ta bir over-booking olursa stop-sale’in push edildiğini kanıtlayan canlı drill yok.
- **BLOCKER — Over-booking detection alerting yok**: `backend/tests/test_overbooking_prevention_e2e.py` mantığı `reconciliation_engine`’e “alerting task” olarak entegre edilmemiş; tespit ediliyor ama operatöre uyarı kanalı (Slack/email/in-app) hooked değil.
- **MEDIUM — Pilot otel sync frequency tuning**: `sync_scheduler.py` default frequency’si pilot otelin OTA volume’una göre tune edilmemiş.

### Sahibi: Channel Manager Squad
### Pilot-blocker mı: **Evet (3 madde)**

---

## 6. Seed / Demo Data

### Mevcut durum
- **Auto-seed**: `backend/bootstrap/phases/b_seed.py` — `auto_seed_if_empty(_raw_db)` (production’da `ALLOW_AUTO_SEED_IN_PROD=1` gerekli).
- **Demo tenant**: `backend/scripts/ensure_demo_user.py` — `hotel_id=100001`, `username=demo`, `password=demo123`.
- **Onboarding API**: `backend/core/onboarding.py` — 12 adımlı checklist, otomatik tespit (Account → Hotel Info → Rooms → Rates → First Guest/Res → Team → Check-in → Channel Manager → Night Audit → Invoice → Report).
- **Onboarding playbook**: `docs/backend/docs/ONBOARDING_PLAYBOOK.md` — 10 günlük süreç.
- **Go-live runbook**: `docs/procedures/GO_LIVE_RUNBOOK.md` ✅
- **Property profiles**: `backend/domains/admin/property_profiles.py` — 15+ profile (PENSION, CITY_HOTEL, RESORT_SUMMER, BOUTIQUE_HOTEL…).

### Bulgular
- **HIGH — Pilot tenant için profil seçimi belgelenmemiş**: `[PILOT_TENANT_ID]` için hangi `property_profile`? Yanlış profil seçilirse modüller (HK, F&B, MICE, Spa) yanlış set edilir ve sonradan switch zor.
- **MEDIUM — Onboarding playbook 10 gün, pilot için sıkışık olabilir**: Pilot deadline’ı kısa ise kritik adımları (Day 1-3 + Day 5 channel) ön sıraya alacak “fast-track” varyantı yok.
- **LOW — Demo data kirlenmesi**: Demo tenant ile pilot tenant aynı cluster’da; demo’ya yapılan değişiklikler pilot’u etkilemez (tenant_id scoping ile) ama UX confusion için pilot operatörlerine demo tenant credential’ı verilmemeli.
- **LOW — `create_test_user.py` üretimde çalışmamalı**: `backend/scripts/` altında; production guard kontrol edilmeli.

### Sahibi: Onboarding / PM
### Pilot-blocker mı: **Hayır** — ama profil seçimi pilot başlangıç gününden önce karar verilmeli.

---

## 7. Known Gaps (Gotcha + TODO/FIXME envanteri)

### TODO/FIXME taraması
- **Toplam**: ~9 marker (backend + frontend), oldukça temiz.
- **Önemli olanlar**:
  - `backend/AGENCY_INTEGRATION_GUIDE.md` — 5 adet (dokümantasyon, kod değil).
  - `backend/core/guest_name_utils.py` — 1 adet.
  - `frontend/src/pages/ChannelConnections.jsx` — 1 adet.
  - E2E test’lerde 2 adet (v1, v2 — refactor notları, blocker değil).
- **Skip/xfail**: `_quarantine/` haricinde 8 adet `test_b2b_webhooks`, 11 adet `battle/sprint2`, 6 adet `test_connection_test_detailed` — bunların pilot etkisi için sahibi belirlenmeli.

### `replit.md` gotcha’ları → pilot sınıflandırma

| Gotcha | Sınıf | Notu |
|---|---|---|
| MongoDB Atlas 500-collection limit | **BLOCKER** | Workaround uygulanmış (embedded array + discriminator); pilot’ta yeni koleksiyon eklenmemeli. |
| Production Secret Management (JWT_SECRET vb.) | **BLOCKER** | Replit Secrets vault’tan gelmeli; `.replit:userenv.shared` plaintext değil. |
| `EXELY_IP_WHITELIST` üretimde | **BLOCKER** | Pilot Exely IP’leri eklensin. |
| API Call Conventions (`/api/` ile/`/api/` olmadan) | HIGH | Geliştirici hatası riski; pilot’ta yeni feature eklenirse code review. |
| JWT Lifespan (15dk default → 7gün override) | HIGH | Pilot’ta refresh token rotation çalışıyor mu doğrula. |
| CORS Configuration | HIGH | Pilot domain’i `CORS_ORIGINS`’e eklenmeli. |
| Night Audit N+1 issues | MEDIUM | Optimize edilmiş ama pilot büyüklüğüne göre tekrar profil. |
| Outbound HTTP Calls (DNS rebinding guard) | MEDIUM | Aktif; pilot’ta tenant-config edilen URL’ler bu hat üzerinden gitmeli. |
| Walk-in Placeholder Guest Names | LOW | UX, blocker değil. |
| Color Palette `purple→indigo` | LOW | Kozmetik. |
| Pages Layout Wrap (118/123 migrated) | LOW | 5 sayfa intentional kalmış. |
| WS Redis Pub/Sub Circuit Breaker | LOW | Aktif. |
| HotelRunner Pull Retries | LOW | Tune edilmiş. |
| Auth Cache Invalidation (Redis pub/sub) | LOW | Aktif. |
| In-App Dialog System (`dialogs.js`) | LOW | Konvansiyon. |
| Image Uploads validation | LOW | Aktif. |

### Sahibi: PM
### Pilot-blocker mı: **Evet (3 madde — yukarıdaki BLOCKER’lar)**

---

## 8. Operasyonel Gözlemlenebilirlik

### Mevcut durum
- **Logging**: `backend/bootstrap/observability_init.py` — structured. Sentry: `infra/cloud_observability.py`. ✅
- **Metrics**: `/api/metrics` Prometheus endpoint, `infra/prometheus/prometheus.yml`. OpenTelemetry desteği bootstrap’ta. ✅
- **Channel manager observability**: `backend/channel_manager/application/observability_service.py` — health trend aggregation.
- **Alert kuralları**: `infra/prometheus/alerts.yml` — `BackendDown`, `HighErrorRate`, `RedisDown`, `MongoHighConnections`, `WorkerQueueBacklog`. ✅
- **Production go-live API**: `/api/production-golive/readiness` skor + sağlık kontrolleri.

### Bulgular
- **HIGH — Sentry’ye debug trafik karışıyor**: Bugün gözlendi (`p-aab2289a@test.local` validation error — benim probe’umdan). Pilot başlamadan önce Sentry’de **environment ayrımı** (`development` vs `pilot` vs `production`) net hale getirilmeli; yoksa pilot operatörlerinin gerçek hatası dev gürültüsünde kaybolur.
- **HIGH — Alertmanager hedefi yok**: `alerts.yml` kuralları var ama `alertmanager` config’in pilot operatörlerine (Slack/email/PagerDuty) hangi kanaldan gideceği `infra/alertmanager/` altında pilot için instantiate edilmemiş.
- **MEDIUM — `/api/production-golive/readiness` pilot threshold’u**: Skor’un kaç olması GO sayılır tanımsız.
- **LOW — Grafana dashboard pilot widget’ı**: `infra/grafana/` altında pilot tenant’a özel dashboard yok; default + tenant filter kullanılacaksa OK.
- **LOW — Log retention politikası**: dokümante değil (Sentry default 30/90 gün?).

### Sahibi: SRE / DevOps
### Pilot-blocker mı: **Hayır** — ama Sentry environment ayrımı pilot başlamadan 1 gün önce yapılmalı.

---

## Önerilen sıralı aksiyon listesi (pilot’tan geri sayım)

| # | Aksiyon | Sahibi | Tahmin |
|---|---|---|---|
| 1 | Pilot tenant kimliği + property_profile karar | PM | 1 saat |
| 2 | `EXELY_IP_WHITELIST` pilot Exely IP’leriyle Replit Secrets’a | DevOps | 30 dk |
| 3 | `JWT_SECRET`, `CM_MASTER_KEY_CURRENT` `.replit:userenv.shared` → Replit Secrets vault | DevOps | 1 saat |
| 4 | Frontend Vitest CI gate ekle | Platform | 2 saat |
| 5 | `deploy/SMOKE.md` + `deploy/smoke.sh` (6 adımlı post-deploy smoke) | DevOps | 3 saat |
| 6 | Tenant-bazlı restore drill (boş staging’de) + `TENANT_RESTORE_DRILL.md` | DevOps | yarım gün |
| 7 | CM sandbox simulation’a “Stop-sale push” + “No-show sync” senaryoları | CM Squad | 1 gün |
| 8 | Over-booking detection → alerting (Slack/email) hook | CM Squad | 1 gün |
| 9 | Sentry environment ayrımı (`pilot`) + Alertmanager pilot kanalı | SRE | 4 saat |
| 10 | v5 cross-tenant E2E (8 yüzey: payment, check-in, check-out, kiosk, IoT, night-audit, tenant-users, granted-permissions) | Backend/QA | 1 oturum |
| 11 | `_quarantine/` envanteri + sahip ataması | QA | 2 saat |
| 12 | Pilot domain’i `CORS_ORIGINS`’a + smoke koş | DevOps | 30 dk |

**Hard-blocker setinin (#2, #4, #6) tamamlanması = ~1 iş günü**.
**Önerilen tüm aksiyonlar (1–12) = ~5 iş günü**.

---

## Açık sorular (pilot başlamadan önce karar lazım)

1. Pilot otelin `property_profile`’ı hangisi olacak? (CITY_HOTEL / BOUTIQUE_HOTEL / RESORT_SUMMER / başka)
2. Pilot çalışma süresi ne kadar (1 hafta gözlem mi, açık uçlu mu)?
3. Pilot rollback eşiği ne? (Örn: “2 saat içinde 3 BLOCKER hata → demo tenant’a geri dön”)
4. Pilot operatörlerine hangi modüller görünür? (Modules toggle’ı önceden set edilecek mi?)
5. v5 cross-tenant testi pilot’tan ÖNCE mi PARALEL mi koşulacak?
6. Channel manager pilot’ta hangi OTA(lar) bağlı? (Exely + HotelRunner ikisi de mi, yoksa bir tanesi mi?)
7. Pilot tenant verisini KİM yedekler ve KİM restore’a yetkili?
8. Sentry pilot environment’a ayrı kota tanımlı mı (yoksa shared dev kotasını yer mi)?

---

**Kapanış**: Bu doküman discovery turunun çıktısıdır. Onaylanırsa bir sonraki adım — ChatGPT ile birlikte — yukarıdaki 12 aksiyonu sıraya koyup hangisinin hangi turda yapılacağını planlamak.
