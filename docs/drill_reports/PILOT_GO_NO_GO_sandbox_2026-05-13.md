# Syroce PMS — HotelRunner Pilot Go / No-Go Şablonu

> **Bu dosya bir ŞABLONDUR.** Her HR pilot turu için kopyala:
> `cp docs/PILOT_GO_NO_GO_HR_TEMPLATE.md docs/drill_reports/PILOT_GO_NO_GO_<tenant_slug>_<YYYY-MM-DD>.md`
>
> Doldurulacak placeholder'lar: `<HR_PILOT_TENANT_ID>`, `<HR_PILOT_TENANT_SLUG>`, `<PILOT_DOMAIN>`, `<PILOT_API_DOMAIN>`, `<PILOT_DATE>`, `<PILOT_LEAD>`, `<PILOT_ADMIN_EMAIL>`.
>
> Genel form için → `docs/PILOT_GO_NO_GO.md`. Bu kopya **HotelRunner-only** pilot için Exely satırlarını N/A işaretler ve HR-specific kontrolleri öne çıkarır.

---

## Pilot Tanımı

| Alan | Değer |
|---|---|
| **Pilot tipi** | HotelRunner canlı CM pilot |
| **Pilot tenant ID** | `<HR_PILOT_TENANT_ID>` |
| **Pilot tenant slug** | `<HR_PILOT_TENANT_SLUG>` |
| **Pilot tarih** | `<PILOT_DATE>` |
| **Pilot Lead** | `<PILOT_LEAD>` |
| **Frontend domain** | `https://<PILOT_DOMAIN>` |
| **Backend API domain** | `https://<PILOT_API_DOMAIN>` |
| **Aktif OTA bağlantıları** | ☑ HotelRunner ☐ Exely (N/A) ☐ Diğer: ___ |
| **Property profile** | ☐ CITY_HOTEL ☐ BOUTIQUE_HOTEL ☐ RESORT_SUMMER ☐ Diğer: ___ |

---

## 1. Özet Tablo (one-page view)

| #  | Kategori     | Kontrol                                       | Owner             | Tip   | Status | Sign-off | Tarih |
|----|--------------|-----------------------------------------------|-------------------|-------|--------|----------|-------|
| 1  | Security     | EXELY whitelist verdict                       | DevOps            | **N/A** (Exely yok) | ☐ N/A | — | — |
| 2  | Infra        | Tenant restore drill                          | DevOps            | Hard  | ☐      |          |       |
| 3  | Tests        | Frontend Vitest gate                          | Frontend          | Hard  | ☐      |          |       |
| 4  | Tests        | Backend hardening + isolation pytest          | Backend           | Hard  | ☐      |          |       |
| 5  | Tests        | v5 Tenant Isolation Core Surface (12 test)    | Backend           | Hard  | ☐      |          |       |
| 6  | Infra        | CI green (ci-cd + frontend-quality)           | DevOps            | Hard  | ☐      |          |       |
| 7  | Infra        | Post-deploy smoke (deploy/smoke.sh 6/6)       | DevOps            | Hard  | ☐      |          |       |
| 8  | Integration  | Sentry / observability active                 | DevOps            | Hard  | ☐      |          |       |
| 9  | Security     | CORS pilot domain whitelisted                 | DevOps            | Hard  | ☐      |          |       |
| 10 | Config       | Pilot tenant profile aligned                  | Pilot Lead / PM   | Hard  | ☐      |          |       |
| 11 | Integration  | **HotelRunner CM scope + sync cadence**       | Backend (CM)      | Hard  | ☐      |          |       |
| 11a| Integration  | **HR no-show outbox parity (Turu #3a + #3b)** | Backend (CM)      | Hard  | ☐      |          |       |
| 11b| Integration  | **HR conflict queue + bulk resolve smoke**    | Backend (CM)      | Hard  | ☐      |          |       |
| 11c| Integration  | **Stop-sale circuit breaker observability**   | Backend (CM)      | Hard  | ☐      |          |       |
| 12 | Security     | Production secrets startup-check              | DevOps            | Hard  | ☐      |          |       |
| 13 | Infra        | MongoDB Atlas indexes ready                   | DevOps            | Hard  | ☐      |          |       |
| 14 | Ops          | Rollback plan rehearsed (last 24h)            | DevOps            | Hard  | ☐      |          |       |
| 15 | Ops          | On-call rotation + paging configured          | Pilot Lead        | Hard  | ☐      |          |       |
| 16 | Security     | KVKK / GDPR data-handling sign-off            | Legal / Pilot Lead| Hard  | ☐      |          |       |
| 17 | Ops          | Pilot user training delivered + acknowledged  | Pilot Lead        | Soft  | ☐      |          |       |
| 18 | Ops          | Support inbox + escalation matrix live        | Pilot Lead        | Soft  | ☐      |          |       |
| 19 | Ops          | Runbook erişimi (`/api/ops/runbooks` 200)     | Pilot Lead        | Soft  | ☐      |          |       |

> **HR pilot kararı**: 16 Hard satırın hepsi PASS olmalı (#1 N/A sayılır → 15 Hard PASS gerekli). Soft FAIL → Pilot Lead notu ile devam.

**Karar (Pilot Lead imzası):** ☐ GO  ☐ NO-GO  ☐ DELAY

> Pilot Lead: __________________________  Tarih: ____________  İmza: __________

---

## 2. HR-spesifik kontroller (genel formdan farklı olanlar)

### #1 — EXELY whitelist verdict · **N/A** (HR-only pilot)

Bu pilot turunda Exely connector aktif değil. `EXELY_IP_WHITELIST` env değişkeni production'da hâlâ set edilmesi gerekmiyor — `exely_webhook_router.py` 503 dönerse OK (kimse webhook çağırmıyor). Pilot tenant'ın connector listesinde Exely seçili olmadığı `#10` ve `#11` ile teyit edilir.

> **Kayıt için** (sign-off zorunlu değil):
> ```bash
> curl -s -H "Authorization: Bearer $TOKEN" \
>   https://<PILOT_API_DOMAIN>/api/channel-manager/connections \
>   | jq '[.[] | select(.provider == "exely")] | length'
> # Beklenen: 0
> ```

---

### #11 — HotelRunner CM scope + sync cadence · Integration · Hard · Backend (CM)

**Verification**:
```bash
# 1a) Sync interval (per-provider scheduler base)
grep -nE "_interval_seconds *=" backend/domains/channel_manager/sync_scheduler.py

# 1b) HR retry policy (manual=3, scheduled=2 — instantiation, NOT module-level)
grep -nE "retries = 3 if is_manual else 2|HotelRunnerProvider\\(.*max_retries" \
  backend/domains/channel_manager/providers/sync_scheduler.py

# 2) Pilot tenant'ın HR connection'ı aktif mi
curl -s -H "Authorization: Bearer $TOKEN" \
  https://<PILOT_API_DOMAIN>/api/channel-manager/connections \
  | jq '[.[] | select(.provider == "hotelrunner" and .active == true)] | length'
```

**Expected output**:
```
25:    _interval_seconds = 300  # 5 minutes default
```
```
117:        retries = 3 if is_manual else 2
118:        provider = HotelRunnerProvider(token=token, hr_id=hr_id, max_retries=retries)
```
```
1
```

> **Not**: Retry policy `providers/sync_scheduler.py:117-118` içinde `pull_for_tenant` instantiation'ında set edilir — module-level constant değildir. digitalocean.md gotcha "HotelRunner Pull Retries" bu konumu gösterir.

**Notes**:
- digitalocean.md gotcha "HotelRunner Pull Retries": manual=3, scheduled=2. Scheduled retries 0 değil → transient 504 kendiliğinden absorb edilir.
- HR token DigitalOcean Secrets'ta `HR_TOKEN` olarak; demo değer prod boot'unda reddedilir (PRE_DEPLOY_CHECKLIST adım 1).
- Sync cadence pilot otelin OTA volume'una göre tune edilebilir (`sync_scheduler.py` — pilot süresi içinde gözlem).

---

### #11a — HR no-show outbox parity (Turu #3a + #3b) · Integration · Hard · Backend (CM)

**Neden**: HR pilot'ta no-show işaretlendiğinde inventory'nin gerçek-zamanlı HR'a push edildiği doğrulanmalı (oda boşalması OTA'da görünmeli, çift satış riski engellenir).

**Verification** (sandbox'ta — pilot deploy öncesi):
```bash
cd backend && pytest \
  tests/test_reservation_noshow_e2e.py \
  tests/test_overbooking_alert_emission.py \
  tests/test_cm_conflict_queue_api.py \
  -v --timeout=30
```

**Expected output**:
```
test_noshow_emits_booking_noshow_outbox_event PASSED
test_double_noshow_does_not_double_emit_outbox PASSED
test_noshow_releases_room_night_locks PASSED
... (10/10 + 5/5 + 6/6) ...
```

**Notes**:
- digitalocean.md gotcha "CM-Hardening Series": #3a (event production), #3b (HR inventory recompute, Strategy A).
- `outbox_dispatcher.EVENT_TYPE_TO_CM_EVENT["booking.no_show.v1"] = "booking_no_show"`.
- HR provider'da transactional booking metodu YOK → cancel ve no-show ikisi de `inventory recompute` patternine düşer (aynı kod yolu).
- Detay → `docs/adr/2026-05-cm-hardening.md`.

---

### #11b — HR conflict queue + bulk resolve smoke · Integration · Hard · Backend (CM)

**Neden**: Overbooking durumunda `conflict_queue` API ve UI iş akışı pilot operatöre çalışır vaziyette teslim edilir.

**Verification** (deploy sonrası):
```bash
# 1) API erişimi
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://<PILOT_API_DOMAIN>/api/channel-manager/conflicts?limit=1" \
  | jq '.items | type'

# 2) UI rota erişimi (smoke browser)
# https://<PILOT_DOMAIN>/channel-manager/conflicts → 200 + tablo render
```

**Expected output**:
```json
"array"
```
+ pilot operatör browser'dan listeyi açabiliyor (manuel, screenshot ekle).

**Notes**:
- Turu #1a (alert emission) + #1b (queue API) + #1c (UI) + #2 (bulk resolve) hepsi merge edildi.
- Bulk resolve idempotency: aynı conflict iki kez resolve edilirse 409, race log'lanır.

---

### #11c — Stop-sale circuit breaker observability · Integration · Hard · Backend (CM)

**Neden**: Persistent HR outage (504 flood / DNS) sırasında log/CPU spam'i CircuitBreaker durdurmalı; pilot operatör pillBanner'dan görmeli.

**Verification** (deploy sonrası):
```bash
# 1) Endpoint canlı + RBAC çalışıyor
curl -s -H "Authorization: Bearer $TOKEN" \
  https://<PILOT_API_DOMAIN>/api/channel-manager/unified-rate-manager/circuit-breakers \
  | jq '{count: (.breakers | length), states: [.breakers[].state] | unique}'

# 2) Frontend pillBanner sadece CLOSED-değil iken görünür
# /channel-manager/unified-rate-manager → pilot başlangıçta hiç banner yok (hepsi CLOSED)
```

**Expected output** (pilot başlangıcında):
```json
{"count": 1, "states": ["CLOSED"]}
```

**Notes**:
- Turu #4 detay → `docs/adr/2026-05-cm-hardening.md`.
- Defaults: `failure_threshold=5`, `recovery_timeout=60s`, `half_open_max_calls=3`.
- Pillbanner severity: OPEN > HALF_OPEN > CLOSED; sadece OPEN/HALF_OPEN render.
- Bulk update toast: `channel_push_count > 0 && breaker open` ise warning.

---

### #14 — Rollback plan rehearsed · Ops · Hard · DevOps

**HR-specific not**: Rollback senaryosunda HR sync scheduler'ı önceki versiyonda da aynı tenant_id ile çalışır → çift push riski yok (idempotency: `uniq_tenant_msg_partner` index, `backend/integrations/xchange/bus.py:158`). Ama HR push queue'sundaki in-flight message'ların hangi sürümle gönderildiği audit edilmeli (Sentry tag `service_version`).

---

## 3. Hızlı koşum (one-shot dry-run, HR pilot için)

```bash
# 3+4+5. Tests (sandbox'ta — deploy öncesi green-light)
cd frontend && yarn test && cd ..
cd backend && pytest \
  tests/test_hardening_comprehensive.py \
  tests/test_production_blockers.py \
  tests/test_v5_tenant_isolation_core_surface.py \
  tests/test_cm_conflict_queue_api.py \
  tests/test_provider_circuit_breaker.py \
  tests/test_overbooking_alert_emission.py \
  -v --timeout=30 && cd ..

# Cross-tenant ve no-show E2E live server fixture gerektirir → sandbox'ta
# pre-existing timeout normal; staging'de koşulmalı:
cd backend && pytest \
  tests/test_cross_tenant_isolation_e2e.py \
  tests/test_reservation_noshow_e2e.py \
  -v --timeout=60

# 7. Smoke (HR pilot için Exely sub-check beklenmez)
BASE_URL=https://<PILOT_API_DOMAIN> \
  ADMIN_EMAIL="<PILOT_ADMIN_EMAIL>" \
  ADMIN_PASSWORD="$PILOT_ADMIN_PASS" \
  READINESS_THRESHOLD=85 \
  bash deploy/smoke.sh
```

İkinci tur (deploy sonrası, prod token gerekli):

```bash
TOKEN=$(curl -s -X POST https://<PILOT_API_DOMAIN>/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"<PILOT_ADMIN_EMAIL>\",\"password\":\"$PILOT_ADMIN_PASS\"}" \
  | jq -r .access_token)

# #11 — HR connection aktif mi
curl -s -H "Authorization: Bearer $TOKEN" \
  https://<PILOT_API_DOMAIN>/api/channel-manager/connections \
  | jq '[.[] | select(.provider == "hotelrunner" and .active == true)] | length'

# #11b — Conflict queue API canlı
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://<PILOT_API_DOMAIN>/api/channel-manager/conflicts?limit=1" \
  | jq '.items | type'

# #11c — Circuit breakers CLOSED
curl -s -H "Authorization: Bearer $TOKEN" \
  https://<PILOT_API_DOMAIN>/api/channel-manager/unified-rate-manager/circuit-breakers \
  | jq '{count: (.breakers | length), states: [.breakers[].state] | unique}'

# #1 sanity (Exely yok)
curl -s -H "Authorization: Bearer $TOKEN" \
  https://<PILOT_API_DOMAIN>/api/channel-manager/connections \
  | jq '[.[] | select(.provider == "exely")] | length'
# → 0 olmalı
```

---

## 4. Karar matrisi (HR pilot)

| Hard FAIL sayısı | Soft FAIL sayısı | Karar           |
|------------------|------------------|-----------------|
| 0                | 0                | **GO**          |
| 0                | ≥1               | GO (Pilot Lead notu zorunlu) |
| ≥1               | herhangi         | **NO-GO** veya DELAY |

> N/A satırlar (#1) hesaba katılmaz.

**Pilot Lead son imza:**

```
GO     ☐
NO-GO  ☐
DELAY  ☐  (yeni hedef tarih: __________)

İmza: __________________   Tarih: __________   Saat: __________
```

---

## 5. Rollback trigger checklist (ilk 24 saat post-go-live, HR pilot)

| Sinyal                                                     | Eşik (10 dk pencere) | Aksiyon                  |
|------------------------------------------------------------|----------------------|--------------------------|
| HTTP 5xx oranı                                             | ≥ %5                 | Otomatik rollback başlat |
| `/health/ready` 503                                        | ≥ 3 ardışık          | Rollback + DB inceleme   |
| Cross-tenant veri sızıntısı (Sentry tag `tenant_leak`)     | ≥ 1                  | **Rollback + acil incident** |
| Login başarı oranı düşüşü                                  | < %95                | İnceleme; auth/JWT kontrol |
| Atlas connection pool tükenmesi                            | %90+                 | Rollback + Atlas tier yükselt |
| **HotelRunner sync error rate**                            | ≥ %20                | CM'i pas geç, manuel mod |
| **HotelRunner circuit breaker OPEN > 5 dk**                | OPEN sürekli         | İnceleme; HR gateway durumu kontrol |
| **Conflict queue derinliği**                               | > 20                 | İnceleme; bulk resolve sürüyorsa OK |
| **Outbox dispatcher backlog**                              | > 100                | İnceleme; Redis sağlık |
| Response p95 latency                                       | > 3s                 | İnceleme; gerekirse rollback |
| Sentry yeni `ERROR` rate                                   | ≥ 10/dk              | İnceleme; tetikleyiciye göre rollback |

**Rollback komutu**:
```bash
bash deploy/rollback.sh            # tek komut — last_good_tag'e döner + smoke koşar
                                   # detay: docs/ROLLBACK.md
```

**RTO hedefi**: < 5 dk.

**Post-rollback zorunlu**:
1. Incident kanalında bildirim
2. `docs/drill_reports/<timestamp>_<HR_PILOT_TENANT_SLUG>_rollback.md` doldur
3. KVKK 72-saat eşiği başladıysa Legal'e haber ver

---

## 6. Bilinen sandbox limitleri (HR pilot için kayıt)

Aşağıdaki testler **dev sandbox'ta live server fixture gerektirdiği için timeout** alabilir. Pilot deploy ortamı (staging veya pilot-prod) bu fixture'ları sağlar; sandbox sonucu **regression değildir**:

- `tests/test_cross_tenant_isolation_e2e.py` — live test server gerek
- `tests/test_reservation_noshow_e2e.py` — live test server gerek
- `tests/battle/test_sprint2_*` — replica-set MongoDB gerek
- `tests/test_atomic_checkin_checkout` — replica-set MongoDB gerek

Pilot deploy öncesi staging'de koşum zorunlu (PILOT_GO_NO_GO #6 CI green satırı bu CI run'ını kapsar).

---

## 7. Referanslar

- `docs/PILOT_GO_NO_GO.md` — genel form (bu dosya o formun HR-specific türevidir)
- `docs/PILOT_READINESS_CHECKLIST.md` — operasyonel detay + hard-blocker tarihçesi
- `deploy/SMOKE.md` — post-deploy 6 adımlı smoke runbook
- `deploy/DEPLOYMENT_GUIDE.md` — deploy + rollback adımları
- `docs/adr/2026-05-cm-hardening.md` — CM-Hardening Turu #1a–#4 + #3c discovery
- `docs/adr/2026-05-production-hardening.md` — No-show terminal-state guard, lock release, folio refund/void guard
- `digitalocean.md` — gotcha'lar (HR Pull Retries, JWT lifespan, Atlas 500-collection limiti, vb.)

---

> **Bu dosya canlı şablondur.** HR pilot turuna özel kopyayı `docs/drill_reports/` altına imzalı arşivle.
