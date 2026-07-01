# Pilot Production Launch Rehearsal

**Audience:** pilot operator + DevOps lead.
**When to use:** T-24h ile T-1h arası, gerçek pilot trafiğini açmadan önce.
**Goal:** "Production Safety Pack 8/8" yazılı altyapının gerçek ortamda
çalıştığını **canlı trafikten önce** kanıtlamak. 30-60 dakika sürer.
**Success criterion:** §0'daki 9 kontrol kapısı PASS olmadan pilot
trafiği AÇILMAZ.

---

## §0 — Tek-bakışta kapı tablosu

| # | Kapı                             | Sahip      | Süre  | Hard | Sandbox kanıtı |
|---|----------------------------------|------------|-------|------|----------------|
| 1 | DigitalOcean Secrets matrix tamamlandı  | DevOps     | 5 dk  | ✅   | §1             |
| 2 | Sentry UI 11 alarm kurulu         | DevOps     | 15 dk | ✅   | §2             |
| 3 | Sentry Crons (cm-backlog) kurulu  | DevOps     | 5 dk  | ✅   | §2.4           |
| 4 | Slack/PagerDuty routing canlı     | DevOps     | 10 dk | ✅   | §3             |
| 5 | `rollback.sh --dry-run` PASS      | DevOps     | 2 dk  | ✅   | §4.1           |
| 6 | `cm_backlog_alert.py --json` PASS | DevOps     | 1 dk  | ✅   | §4.2           |
| 7 | `verify_atlas_backup.py` PASS     | DevOps     | 1 dk  | ✅   | §4.3           |
| 8 | `deploy/smoke.sh` 6/6 PASS        | DevOps     | 3 dk  | ✅   | §4.4           |
| 9 | `PILOT_GO_NO_GO_HR_<slug>.md` doldu | Pilot Lead | 30 dk | ✅ | §5             |

Bir tek **Hard** kapı FAIL → pilot trafiği AÇMA, §6 eskalasyon zinciri.

---

## §1 — DigitalOcean Secrets checklist

Vault: Workspace → Tools → Secrets. **ASLA terminal'den `export ...` yapma**
— workflow restart'ında kaybolur. Kıyaslama: `python -c "import os;
print([k for k in ['ATLAS_TIER','SENTRY_ENVIRONMENT','SENTRY_DSN'] if os.environ.get(k)])"`.

### 1.1 Zorunlu (eksiklik = startup FAIL veya hard-blocker)

| Secret                  | Beklenen değer / format               | Kontrol                                      |
|-------------------------|----------------------------------------|----------------------------------------------|
| `JWT_SECRET`            | ≥32 karakter random                    | `readiness.checks.jwt_secret`                |
| `JWT_EXPIRATION_MINUTES`| `10080` (7 gün, default 15 override)   | `digitalocean.md` Auth gotcha                      |
| `MONGO_ATLAS_URI`       | `mongodb+srv://...mongodb.net/...`     | atlas backup check `.mongodb.net` algılar    |
| `ATLAS_TIER`            | `M10` (M0 + production → readiness FAIL)| `readiness.checks.backup`                   |
| `SENTRY_DSN`            | `https://...@sentry.io/...`            | `readiness.checks.sentry_active`             |
| `VITE_SENTRY_DSN`       | (frontend) — aynı project, farklı key  | browser console `Sentry.init`                |
| `SENTRY_ENVIRONMENT`    | `pilot` (default `production`, pilot için override) | `cloud_observability.py` env tag |
| `RESEND_API_KEY`        | `re_...`                               | mailing testleri                             |
| `RESEND_FROM`           | `noreply@<domain>`                     | mailing testleri                             |
| `CORS_ORIGINS`          | `https://<frontend-domain>` (virgül ayraç) | preflight testi                          |
| `EXELY_IP_WHITELIST`    | virgül ayraçlı IP'ler (CIDR DEĞİL)     | `verify_exely_whitelist.py --env production` |
| `ROOM_QR_SECRET`        | ≥32 karakter random                    | room QR token üretimi                        |
| `PUBLIC_APP_URL`        | `https://<frontend-domain>`            | email link'leri, OAuth callback              |

**HotelRunner credentials** (HR-only pilot için zorunlu): tenant başına
encrypted credentials DB'de, env-var DEĞİL — `digitalocean.md` "CapX
Integration" + ADR `2026-05-cm-hardening.md`.

### 1.2 Opsiyonel (eksiklik = degraded ama startup OK)

| Secret                                           | Etkisi                                 |
|--------------------------------------------------|----------------------------------------|
| `ATLAS_API_PUBLIC_KEY` + `_PRIVATE_KEY` + `_PROJECT_ID` + `_CLUSTER_NAME` | snapshot tazelik doğrulaması; yoksa `verify_atlas_backup.py` no-op exit 0 |
| `SENTRY_AUTH_TOKEN` + `_ORG_SLUG` + `_PROJECT_SLUG` | release tracking + source maps         |
| `EXELY_TRUSTED_PROXY_IPS`                        | XFF proxy resolution (CIDR OK)         |
| `EXELY_TRUST_FORWARDED`                          | `1` → XFF header güven                 |
| `ENABLE_SETUP_ENDPOINTS`                         | **PİLOTTA `0` veya unset** (deploy öncesi setup yapıldı) |
| `ENABLE_QUICKID_DEMO`                            | **PİLOTTA `0` veya unset** (gerçek QuickID kullanılır)   |
| `DISABLE_EXPO_PUSH`                              | `0` veya unset (push aktif)            |
| `DISABLE_AUTH_THROTTLE`                          | **PİLOTTA `0` veya unset**; set edilse bile prod_guard yoksayar |

### 1.3 Doğrulama tek-komut

```bash
# DigitalOcean Shell:
curl -fsS http://localhost:8000/api/production-golive/readiness | jq '.verdict, .score, .checks | keys'
# Beklenen: "PASS" veya "REVIEW", score ≥ 0.8, 12+ check key
```

---

## §2 — Sentry UI checklist (manuel kurulum)

**Doc:** `docs/SENTRY_ALERT_POLICY.md` — 11 alarm routing tablosu + severity
matrix. Bu §2 sadece **operatör tıklama sıralaması**.

### 2.1 Project ayarları

1. Sentry → Settings → Projects → `<project>` → **General**
2. Platform: Python (backend) + JavaScript-React (frontend) — iki ayrı project
3. **Data Scrubbers**: hepsi açık (`Default Pii`, `Credit Cards`, `Tokens`,
   `IP Addresses`)
4. **Environment**: backend init zaten `SENTRY_ENVIRONMENT=pilot` okur

### 2.2 11 Alarm rule (Settings → Alerts → Create Alert Rule)

`docs/SENTRY_ALERT_POLICY.md` §3 routing tablosundan kopyala. Her rule
için: **Name**, **When (filter)**, **Then (action)** üçlüsü:

| # | Rule adı                        | Filter (`tags`)                              | Action          |
|---|---------------------------------|----------------------------------------------|-----------------|
| 1 | tenant_leak                     | `subsystem:rls level:fatal`                  | PagerDuty CRIT  |
| 2 | 5xx burst                       | `level:error count > 50/5min`                | PagerDuty CRIT  |
| 3 | HotelRunner sync fail           | `subsystem:hotelrunner level:error`          | Slack #pms-alerts|
| 4 | Outbox FAIL                     | `subsystem:cm-backlog level:error`           | Slack + email   |
| 5 | Outbox sampler error → fatal    | `subsystem:cm-backlog level:fatal`           | PagerDuty       |
| 6 | CB OPEN ≥3                      | `subsystem:cm-circuit level:error`           | Slack + email   |
| 7 | Atlas backup stale              | `subsystem:atlas-backup level:error`         | DBA queue       |
| 8 | KVKK violation                  | `subsystem:kvkk level:error`                 | KVKK officer    |
| 9 | JWT weak / brute-force          | `subsystem:auth level:warning count > 100/h` | Security team   |
|10 | ChunkLoadError (frontend)       | `subsystem:frontend message:ChunkLoad`       | Slack #pms-alerts|
|11 | Payment failure                 | `subsystem:payment level:error`              | Finance + DBA   |

### 2.3 Smoke test (her rule için)

Backend Shell:
```python
import sentry_sdk
sentry_sdk.set_tag("subsystem", "rls")
sentry_sdk.set_tag("test", "rehearsal")   # ZORUNLU — auto-resolve filter için
sentry_sdk.capture_message("REHEARSAL test — rule #1 (tenant_leak)", level="fatal")
```
PagerDuty/Slack'e geldi mi? → ☑. **Auto-clean kuralı (Sentry-UI):**
Settings → Alerts → Create Alert Rule → "When `tags.test == rehearsal`
AND age > 1h → Then: Resolve". Bu kural pilot başlamadan kurulursa
operatör Resolve etmeyi unutsa bile gerçek alarm'lar arasında
rehearsal-test event'i 1 saat sonra otomatik kapanır. Yedek olarak:
test sonrası Sentry UI → Issues → `test:rehearsal` filter → bulk
"Resolve" butonu.

### 2.4 Sentry Crons → cm-backlog monitor

1. Sentry → Crons → Add Monitor
2. **Slug:** `cm-backlog`
3. **Schedule type:** Interval, **every:** 5 minutes
4. **Checkin margin:** 2 minutes, **Max runtime:** 60s
5. Cron komut'una `--sentry-capture` flag ekle:
   ```bash
   */5 * * * * cd /workspace && python backend/scripts/cm_backlog_alert.py --quiet --sentry-capture
   ```
6. Sentry-CLI alternatifi (önerilen):
   ```bash
   */5 * * * * sentry-cli monitors run cm-backlog -- python backend/scripts/cm_backlog_alert.py --quiet
   ```

---

## §3 — Slack / PagerDuty routing

| Kanal               | Yönlendirme                                          |
|---------------------|------------------------------------------------------|
| `#pms-alerts`       | Sentry rules #3, #4, #6, #10 (Slack webhook)         |
| `#pms-pilot-dba`    | Atlas + outbox sampler error (rule #5, #7, #11)      |
| PagerDuty `pms-pilot-oncall` | rule #1, #2, #5 (CRITICAL)                  |
| Email DL `kvkk@<domain>` | rule #8                                          |
| Email DL `security@<domain>` | rule #9                                      |

**Smoke test:** Sentry rule'ları §2.3 gibi tetikle, kanal/alıcılarda gelen
mesajı doğrula. PagerDuty'de alarm Acknowledge + Resolve cycle'ı dene.

---

## §4 — Sandbox script dry-run (canlı öncesi prova)

Aşağıdaki 4 komut sandbox'ta TEST EDİLMİŞ (12 May 2026). Pilot ortamında
aynı komutlar gerçek değer döndürecek — referans çıktı niteliğinde.

### 4.1 `bash deploy/rollback.sh --dry-run`

```text
════════════════════════════════════════════════════════════
  Syroce PMS — Rollback (git-based rebuild)
  Repo root     : /home/runner/workspace
  Compose       : .../deploy/docker-compose.production.yml
  Last-good file: .../deploy/.last_good_tag
[!] DRY-RUN modu — hiçbir komut çalıştırılmaz
════════════════════════════════════════════════════════════
── 1/5 — Hedef commit belirleniyor ──
[FAIL] Hedef yok: .last_good_tag bulunamadı ve argüman geçilmedi
```

**Sandbox'ta `.last_good_tag` YOK** — ilk başarılı `deploy/deploy.sh`
sonrası `deploy/deploy.sh:170-174` dosyayı yazar. Pilot'ta:
```bash
bash deploy/rollback.sh --list      # 10 son commit listele
bash deploy/rollback.sh --dry-run   # last_good var → hedef göster, koşma
bash deploy/rollback.sh             # GERÇEK rollback (smoke.sh otomatik koşar)
```
Pilot kapısı: ilk deploy sonrası **`.last_good_tag` mevcut + `--dry-run`
PASS** olmalı.

### 4.2 `python backend/scripts/cm_backlog_alert.py --json`

Sandbox çıktı (Mongo localhost yok — production'da Atlas'a bağlanır):
```json
{
  "verdict": "unknown",
  "outbox": {"status": "unknown", "score": 0.5, "error_type": "ServerSelectionTimeoutError"},
  "circuit_breakers": {"status": "ok", "score": 1.0, "total": 0, "open": 0, "half_open": 0,
                       "thresholds": {"open_degraded": 1, "open_fail": 3}}
}
```

Pilot'ta beklenen: `verdict=ok`, outbox status `ok|degraded|unknown` ile
score ≥0.8, CB total=0 (hiç push yok henüz). İlk pilot booking'ten
sonra yeniden koş — outbox count + CB durumu gerçek değer döndürür.

### 4.3 `python backend/scripts/verify_atlas_backup.py --max-age-hours 26`

Sandbox çıktı (API key set değil — beklenen no-op):
```text
verify_atlas_backup: api_keys_unset (no-op, exit 0)
```

Pilot'ta API key'ler set ise: `verify_atlas_backup: ok, last_snapshot=...,
age_hours=...`. Doc: `docs/ATLAS_BACKUP_AND_RESTORE.md`.

### 4.4 `bash deploy/smoke.sh` (canlı URL)

```bash
BASE_URL=https://<pilot-api-domain> \
ADMIN_EMAIL=<pilot-admin-email> \
ADMIN_PASSWORD=<one-time-rotate-after> \
bash deploy/smoke.sh
```

6 adım: (1) `/health/ready` 200, (2) login token döner, (3) bookings
list 200, (4) cancel write-check (opsiyonel), (5)
`/production-golive/readiness` verdict, (6) sentry/observability summary.
**Geçer not:** 6/6 PASS.

---

## §5 — PILOT_GO_NO_GO doldurma

Mevcut template:
```bash
cp docs/PILOT_GO_NO_GO_HR_TEMPLATE.md \
   docs/drill_reports/PILOT_GO_NO_GO_<tenant_slug>_$(date +%Y-%m-%d).md
```

Doldurulacak placeholder'lar:
- `<HR_PILOT_TENANT_ID>` — Mongo `tenants` koleksiyonundan kopyala
- `<HR_PILOT_TENANT_SLUG>` — slug (URL-safe)
- `<PILOT_DOMAIN>` — frontend domain
- `<PILOT_API_DOMAIN>` — backend API domain
- `<PILOT_DATE>` — pilot başlangıç tarihi
- `<PILOT_LEAD>` — pilot lead adı
- `<PILOT_ADMIN_EMAIL>` — admin user email

**45 satırlık one-page tablo** (template §1) → her hard satır için owner +
verification command + expected output + sign-off + tarih. Tüm `Hard`
satırlar ☑ olmadan pilot trafiği AÇMAZ.

`docs/drill_reports/` zaten 3 önceki drill içeriyor (T1 drill, dry_run
rehearsal, cm_sandbox_discovery) — yeni rehearsal ek satır olur.

---

## §6 — Eskalasyon (kapı FAIL ise)

| FAIL kapısı                           | Aksiyon                                                  |
|---------------------------------------|----------------------------------------------------------|
| §1 zorunlu secret eksik               | DevOps → DigitalOcean Secrets ekle → workflow restart          |
| §2 Sentry rule kurulmadı              | Sentry-UI 15 dk içinde tamamlanabilir, T-1h kapısı       |
| §3 Slack/PD test mesajı gelmedi       | Webhook URL doğrula → Sentry rule "Then" action güncelle |
| §4.1 rollback dry-run FAIL (post-deploy) | DevOps + Pilot Lead — deploy.sh `.last_good_tag` yazıyor mu kontrol |
| §4.2 cm_backlog_alert FAIL            | `docs/CM_OBSERVABILITY.md` §3 senaryo akışı              |
| §4.3 atlas backup stale (>26h)        | DBA queue → Atlas UI snapshot manuel tetikle             |
| §4.4 smoke 1+ adım FAIL               | Adım numarasına göre `docs/REPLIT_OPS_CHEATSHEET.md` §4  |
| §5 GO/NO-GO Hard satır FAIL           | Pilot Lead — pilot tarihini ERTELE                       |

**Hard-stop kuralı (multi-gate):**
- ≥3 Hard kapı FAIL → pilot tarihini **24h ERTELE** (kahramanca tek-tek
  düzeltme YOK; çevre temelde kararsız demek).
- Gate **#1 (Secrets), #5 (Rollback dry-run) veya #8 (smoke 6/6)** tek
  başına FAIL → pilot tarihini **24h ERTELE** (bu üçü canlıda hayatta
  kalma şartı; eksik secret = startup fail, rollback yok = geri dönüş
  yok, smoke fail = base path zaten kırık).
- Diğer tek kapı FAIL → düzelt + yeniden koş, pilot saati erteleme
  şart değil.

**Genel kural:** "Sadece izle" yok. Rehearsal kapısı FAIL → düzelt veya
ertele. T+0 sonrası izleme runbook'u ayrı: `docs/PILOT_FIRST_24H_MONITORING.md`.

---

## §7 — Çapraz-link

- **Operatör nöbet defteri (T+0 sonrası):** `docs/PILOT_FIRST_24H_MONITORING.md`
- **Tek-sayfa OPS referansı:** `docs/REPLIT_OPS_CHEATSHEET.md`
- **Sentry alarm policy:** `docs/SENTRY_ALERT_POLICY.md`
- **Rollback runbook:** `docs/ROLLBACK.md`
- **Atlas backup:** `docs/ATLAS_BACKUP_AND_RESTORE.md`
- **CM observability:** `docs/CM_OBSERVABILITY.md`
- **Kill-switch envanteri:** `docs/KILL_SWITCH_REGISTRY.md`
- **Production safety planı (8/8):** `docs/PRODUCTION_SAFETY_PLAN.md`
- **GO/NO-GO genel form:** `docs/PILOT_GO_NO_GO.md`
- **GO/NO-GO HR template:** `docs/PILOT_GO_NO_GO_HR_TEMPLATE.md`
