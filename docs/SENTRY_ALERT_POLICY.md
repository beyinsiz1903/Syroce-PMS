# Sentry Alert Policy & Routing

> **Pilot HR canlı CM** öncesi Production Safety Pack #4. DSN ve SDK init
> hazır (`backend/infra/cloud_observability.py:90-130` + `frontend/src/index.jsx:11-32`),
> bu doküman **alarm kuralları + routing + severity matrisi + manuel
> Sentry-UI kurulum adımları**'nı netleştirir. "Sistem bir şey yakaladı
> ama kimse haber almıyor" boşluğunu kapatır.
>
> **⚠️ LOCK-STEP:** §3 routing tablosu değişirse `docs/PRODUCTION_LAUNCH_REHEARSAL.md`
> §2.2 (operatör Sentry-UI tıklama listesi) **aynı PR içinde** güncellenmelidir;
> aksi halde rehearsal listesi gerçek policy'den drift eder.

---

## 1. Ortam (Environment) Taksonomisi

Her event Sentry'ye **`environment`** tag'iyle gider; routing kuralları
bu tag'e göre filtre alır.

| Env değeri      | Ne zaman                              | Hangi alarmlar tetiklenir         |
| --------------- | ------------------------------------- | --------------------------------- |
| `development`   | Lokal / DigitalOcean sandbox (default)      | Hiçbiri (dev gürültüsü mute)      |
| `pilot`         | HR pilot tenant'ı, canlı veri         | **Tüm critical + error**          |
| `production`    | Genel availability (post-pilot)       | Tüm critical + error + warning    |
| `staging`       | Pre-prod doğrulama ortamı             | Sadece critical (smoke trigger)   |

**Set edileceği yerler:**
- Backend: `SENTRY_ENVIRONMENT=pilot` (DigitalOcean Secrets, deploy adımı).
  Mevcut default `infra/env.production.template:31`'de `production`,
  `infra/k8s/base.yml:24`'te `production`. Pilot için **DigitalOcean Secrets'a
  `SENTRY_ENVIRONMENT=pilot` ekleyin** (override'ler bu sırada okunur).
- Frontend: `import.meta.env.MODE` otomatik (`development`/`production`).
  Pilot binary'ler `production` build olduğu için `production` döner —
  Sentry-UI'da pilot ayrımını **release tag** üzerinden yapın
  (`SENTRY_RELEASE=pilot-2026.05.12`).

---

## 2. Severity Matrisi

| Severity | Anlam                                         | İlk yanıt SLA     | Kanal                           |
| -------- | --------------------------------------------- | ----------------- | ------------------------------- |
| **CRITICAL** | Müşteri verisi risk altında / sistem kapalı | < 5 dk (page)     | PagerDuty + Slack #pms-incidents |
| **ERROR**    | Bir feature kapalı, fallback yok            | < 30 dk           | Slack #pms-alerts + email       |
| **WARNING**  | Degraded / fallback aktif                   | < 4 saat          | Slack #pms-alerts (weekday)     |
| **INFO**     | Audit / observability                       | Best effort       | Sentry only (no notify)         |

---

## 3. Routing Tablosu

Olay tipi → severity → routing kuralı. Sentry-UI'da **Settings → Alerts**
altında bu satırlar **manuel** kurulur (Sentry CLI alert provisioning
bu pakete dahil değil — manual rules pilot için yeterli).

| Olay tipi                          | Tag filter                                | Severity   | Routing                  | Throttle             |
| ---------------------------------- | ----------------------------------------- | ---------- | ------------------------ | -------------------- |
| `tenant_leak` exception            | `subsystem:rls` OR message ~ "tenant_id"  | CRITICAL   | PagerDuty + #pms-incidents | none (her event)    |
| 5xx burst (>5/min)                 | `level:error` AND `transaction:*`         | CRITICAL   | PagerDuty                | 5-min cooldown       |
| HR sync failure (auth/IP block)    | `subsystem:hotelrunner` AND `severity:error` | ERROR  | #pms-alerts + email      | 15-min cooldown      |
| HR sync transient (504/timeout)    | `subsystem:hotelrunner` AND `severity:warning` | WARNING | #pms-alerts (digest)  | hourly digest        |
| Outbox FAIL (cm_backlog cron)      | `subsystem:cm-backlog` AND `severity:error` | ERROR    | PagerDuty + #pms-alerts  | 30-min cooldown      |
| Outbox sampler error (DB unreachable) | `subsystem:cm-backlog` AND `severity:fatal` | CRITICAL | PagerDuty (DBA queue)  | none                 |
| Circuit breaker OPEN (≥3 providers)| `subsystem:cm-circuit` AND `open>=3`       | ERROR     | #pms-alerts              | 30-min cooldown      |
| Atlas backup snapshot stale (>26h) | `subsystem:atlas-backup` AND `severity:error` | ERROR | #pms-alerts + email      | 12-hour cooldown     |
| KVKK ID photo TTL expiring (<24h)  | `subsystem:kvkk` AND `severity:warning`    | WARNING   | #pms-alerts              | daily                |
| JWT secret weak / dev key in prod  | `subsystem:auth` AND message ~ "weak_jwt"  | CRITICAL  | PagerDuty                | none                 |
| Frontend ChunkLoadError surge      | `level:error` AND message ~ "ChunkLoad"   | WARNING   | #pms-alerts              | 30-min digest        |

---

## 4. Tag Taxonomy (Standardizasyon)

Tüm `capture_error` / `capture_message` çağrıları **bu tag'leri set
etmeli** ki routing rules çalışsın. `cloud_observability.SentryIntegration`
zaten `tags=` kwarg'ını destekliyor; çağrı tarafı şu sözleşmeye uymalı:

| Tag adı       | Zorunlu | Değerler                                                       |
| ------------- | ------- | -------------------------------------------------------------- |
| `subsystem`   | EVET    | `auth`, `rls`, `hotelrunner`, `exely`, `cm-backlog`, `cm-circuit`, `atlas-backup`, `kvkk`, `outbox`, `pms-frontdesk`, `pms-housekeeping`, `payment`, `night-audit` |
| `severity`    | EVET    | `info`, `warning`, `error`, `fatal`                            |
| `tenant_id`   | HAYIR   | **ASLA EKLEMEYİN** — PII; routing tenant-aware OLAMAZ          |
| `property_id` | HAYIR   | Aynı şekilde ASLA                                              |
| `feature_flag`| Opsiyonel | Kill-switch tetikleyebilecek özellik adı (`disable_quickid`)  |

**Örnek (backend):**
```python
from infra.cloud_observability import sentry_integration
sentry_integration.capture_error(exc, tags={
    "subsystem": "hotelrunner",
    "severity": "error",
})
```

**Örnek (frontend):**
```javascript
Sentry.captureException(err, {
  tags: { subsystem: "pms-frontdesk", severity: "error" }
});
```

---

## 5. PII Guard (Defense-in-Depth)

`backend/infra/cloud_observability.py` `before_send` hook'u **her event'te**
şu pattern'leri scrub eder (Sentry'ye ulaşmadan önce):

| Pattern                          | Replace                  |
| -------------------------------- | ------------------------ |
| JWT (`eyJ...` 3 segment)         | `<JWT>`                  |
| Bearer token / `?token=`/`?api_key=`/`?secret=`/`?password=` | `<TOKEN>` / `<REDACTED>` |
| Email (`a@b.c`)                  | `<EMAIL>`                |
| IPv4 (`1.2.3.4` → `1.2.x.4`)     | 3. oktet maskeli         |
| MongoDB ObjectId (24 hex)        | `<OID>` (tenant surrogate) |

**Set edilenler (sentry_sdk.init):**
- `send_default_pii=False` — cookies, request body, IP otomatik strip.
- `before_send=_sentry_before_send` — yukarıdaki pattern scrub.
- Frontend: `replayIntegration({ maskAllText: true, blockAllMedia: true })`
  + `replaysSessionSampleRate: 0.0` (sadece error session replay).

**Kontrol nasıl yapılır:**
1. Pilot deploy sonrası kasti bir test exception fırlatın
   (`raise ValueError("test token=eyJtest123.foo.bar from a@b.c at 1.2.3.4 oid 6543210fedcba9876543210f")`).
2. Sentry-UI'da event'i açın → message + stack trace + breadcrumbs taranır.
3. Beklenti: `<JWT> ... <EMAIL> at 1.2.x.4 oid <OID>`.

---

## 6. cm_backlog_alert.py Cron Entegrasyonu

İki seçenek (ikisi birlikte de kullanılabilir):

### Seçenek A: sentry-cli monitor wrap (önerilen — dış izleme)

Cron'un kendisi de sağlık kanıtı (heartbeat). Cron çalışmazsa Sentry
bunu da bildirir.

```cron
* * * * * /usr/bin/sentry-cli monitors run cm-backlog -- \
    python /app/backend/scripts/cm_backlog_alert.py --json --quiet
```

Sentry-UI:
- **Crons → New Monitor → Slug: `cm-backlog`**
- Schedule: `* * * * *` (every minute)
- Max runtime: 30s
- Failure issue threshold: 1 (single exit-1 raises issue)
- Recovery threshold: 2 (two consecutive OK to resolve)

### Seçenek B: in-process Sentry capture (sentry-cli yoksa)

```cron
* * * * * SENTRY_DSN="$SENTRY_DSN" SENTRY_ENVIRONMENT=pilot \
    python /app/backend/scripts/cm_backlog_alert.py --quiet --sentry-capture
```

`--sentry-capture` flag'i:
- FAIL verdict → `level=error`, `subsystem=cm-backlog`, `severity=error`,
  reasons + counts (no PII) extra'da
- Sampler error (exit 2) → `level=error` (treated as fatal in routing),
  `severity=fatal` → DBA PagerDuty queue
- DEGRADED verdict → Sentry'ye gitmez (cron logs yeterli)

---

## 7. Manuel Kurulum Checklist (Pilot Deploy Öncesi)

- [ ] **DigitalOcean Secrets**: `SENTRY_ENVIRONMENT=pilot` ekle
- [ ] **Sentry-UI → Settings → Projects → syroce-pms-backend**:
  - Inbound filters: enable IP filter for staff bastion IPs
  - Data scrubbing: ek olarak `tenant_id`, `property_id`, `phone_e164`,
    `id_number` field name'lerini `Additional sensitive fields`'e ekle
- [ ] **Sentry-UI → Alerts → New Alert Rule** (yukarıdaki Routing
  Tablosu'ndaki 11 satırı tek tek oluştur)
- [ ] **Sentry-UI → Crons → New Monitor**: `cm-backlog`, schedule
  `* * * * *`, failure threshold 1
- [ ] **Slack**: `#pms-incidents` (CRITICAL) ve `#pms-alerts` (ERROR/WARNING)
  kanallarını oluştur, Sentry Slack integration'ı kur
- [ ] **PagerDuty**: 2 servis oluştur — `pms-pilot-oncall` (genel),
  `pms-pilot-dba` (sampler error / DB-side); rotation politikası kur
- [ ] **Email**: `alerts@syroce.com` group'a yönlendir, ERROR severity
  digest mode (saat başı)
- [ ] **Test event**: PII scrub test exception fırlat (madde 5), sonucu
  doğrula → `<JWT>`, `<EMAIL>`, `1.2.x.4`, `<OID>` görmelisin

---

## 8. Doğrulama (Sandbox + Pilot)

**Sandbox (kod doğrulaması, deploy gerekmez):**
```bash
python3 -m py_compile backend/infra/cloud_observability.py \
                       backend/scripts/cm_backlog_alert.py
python3 -c "
from backend.infra.cloud_observability import _scrub_str
assert '<JWT>' in _scrub_str('token=eyJhbGciOiJIUzI1NiJ9.foo.bar')
assert '<EMAIL>' in _scrub_str('contact a@b.com please')
assert '1.2.x.4' in _scrub_str('from IP 1.2.3.4 blocked')
assert '<OID>' in _scrub_str('tenant 6543210fedcba9876543210f not found')
assert '<TOKEN>' in _scrub_str('Authorization: Bearer abcdef1234567890XYZ')
assert '<REDACTED>' in _scrub_str('GET /x?token=secret123&user=bob')
print('PII scrub PASS')
"
```

**Pilot (deploy sonrası, gerçek event):**
1. Test exception fırlat (madde 5).
2. Sentry-UI'da 1 dk içinde event görün, scrub doğrulanmış olmalı.
3. cm_backlog_alert cron heartbeat: Sentry Crons sayfası `cm-backlog`
   yeşil olmalı.
4. CM panel'de bir provider'ı kasti olarak yanlış URL'e yönlendir →
   5 dakika içinde circuit OPEN → cm_backlog_alert event fırlatmalı →
   Sentry-UI'da `subsystem:cm-circuit` filtresinde görünmeli.

---

## 9. Out of Scope (Sonraki Turlar)

- **Sentry CLI alert provisioning (Terraform-style)**: Manuel UI kurulumu
  pilot için yeterli. Otomasyon → Production hardening pack #6 / #7.
- **Multi-region Sentry org failover**: Tek org, tek region — pilot
  ölçeğinde gerekmez.
- **OpenTelemetry trace → Sentry trace correlation**: OTel zaten init,
  sentry trace_id propagation'ı `traces_sample_rate=0.1` ile çalışır
  ama explicit trace context propagation Q3 2026.
- **Custom Sentry dashboards**: Grafana zaten cluster metrics'i kapsar,
  Sentry dashboard sadece error trends için manuel kurulur.

---

## 10. İlgili Dosyalar

- Backend SDK init: `backend/infra/cloud_observability.py:88-170` (Sentry
  + before_send PII scrub)
- Frontend SDK init: `frontend/src/index.jsx:10-32`
- Cron alert script: `backend/scripts/cm_backlog_alert.py` (`--sentry-capture`)
- Observability source-of-truth: `backend/infra/cm_observability_check.py`
- Production safety plan: `docs/PRODUCTION_SAFETY_PLAN.md` (#4 satırı)
- Atlas backup pair: `docs/CM_OBSERVABILITY.md` (cron senaryoları)
