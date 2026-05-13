# Replit OPS Cheat-Sheet — Pilot HR Canlı CM

> **Tek-sayfa operatör referansı.** Pilot 24/7 nöbet süresince
> "şimdi ne yapmalıyım?" sorusuna 30 saniyede cevap verir. Bağlam ve
> derinlemesine açıklama için referansa bakın (her bölümün altında).
>
> **Hızlı yön:** Sorun → §3 triage → §4 komut → §5 escalate.

---

## 0. Acil Durum Kısayolları

```bash
# Sistem ayağa kalkmıyor / 5xx %50+ → ROLLBACK
bash deploy/rollback.sh                 # son iyi tag'e döner + smoke koşar

# Önce dene (komut çalıştırmaz, sadece gösterir)
bash deploy/rollback.sh --dry-run

# Hangi tag'lere dönebilirim?
bash deploy/rollback.sh --list

# Belirli bir tag'e dön
bash deploy/rollback.sh <git-sha>
```

**Sentry incident link**: Sentry-UI → Issues → Sort by: Last Seen
**PagerDuty rotation**: `pms-pilot-oncall` (genel) / `pms-pilot-dba` (DB-side)

---

## 1. Sağlık Kontrolleri (Health Checks)

### Hızlı tarama (tek komut, 5 sn)

```bash
# Tüm readiness check'ler (cm_outbox + cm_circuit_breakers dahil)
curl -fsS https://<prod-domain>/api/production-golive/readiness | jq

# Sadece CM (outbox + circuit breakers)
python backend/scripts/cm_backlog_alert.py --json
```

### Endpoint matrisi

| Konu                       | Endpoint                                          | Beklenen           |
| -------------------------- | ------------------------------------------------- | ------------------ |
| Genel readiness            | `GET /api/production-golive/readiness`            | `verdict=PASS`     |
| Mongo                      | `GET /api/production-golive/mongo/health`         | `status=ok`        |
| Provider durumları         | `GET /api/production-golive/providers/status`     | per-provider OK    |
| Secrets                    | `GET /api/production-golive/secrets/health`       | tüm critical=true  |
| Observability              | `GET /api/observability/health`                   | sentry+otel active |
| Redis                      | `GET /api/infra/redis/health`                     | `connected=true`   |
| WebSocket                  | `GET /api/health` (websocket health router)       | active counts      |
| CM outbox + breakers       | `python backend/scripts/cm_backlog_alert.py`      | exit 0             |
| CB drill-down (RBAC)       | `GET /api/channel-manager/unified-rate-manager/circuit-breakers` | per-conn |

### Atlas backup tazelik

```bash
# API key varsa snapshot age döner; yoksa no-op exit 0
python backend/scripts/verify_atlas_backup.py --max-age-hours 26
```

---

## 2. Sık Yapılan Eylemler

### Workflow restart (Replit Workflows panel veya komut)

| Workflow         | Ne zaman                                 |
| ---------------- | ---------------------------------------- |
| Backend API      | Backend env-var değişti / 500 spike      |
| Mobile Web       | Frontend env-var değişti                 |
| Quick-ID API     | QuickID 503 / KVKK alert                 |
| Start application| Frontend dev-server donuk                |

**Komut (Replit Shell):** üst-sağ "Restart" butonu, veya:
```bash
# Workflow logs (preview):
tail -100 /tmp/logs/Backend\ API_*.log
```

### Cron alarm manuel çalıştır

```bash
# Detaylı insan output
python backend/scripts/cm_backlog_alert.py

# Cron parity (Sentry'ye de push'la)
SENTRY_DSN="$SENTRY_DSN" SENTRY_ENVIRONMENT=pilot \
  python backend/scripts/cm_backlog_alert.py --quiet --sentry-capture
```

### Index audit (yavaşlık şüphesi)

```bash
python backend/scripts/index_audit.py        # mevcut index analizi
python backend/scripts/index_apply.py        # eksik index'leri ekle
```

### Production DB read-only inspect

> Yazma yapmayın — `database` skill'i ile production query.

```python
# Replit Agent code_execution sandbox'ında:
await checkDatabase({ environment: "production", query: "..." });
```

### Secret düzenle

> **NEVER** secret'i terminal'e print etme. Replit Secrets paneli (sağ menü)
> üzerinden GUI ile düzenle. Değişiklik sonrası Backend API workflow restart.

Pilotta sık değişen secret'ler:
- `SENTRY_ENVIRONMENT` (pilot ↔ production geçişi)
- `JWT_EXPIRATION_MINUTES` (sorun şüphesi varsa düşür)
- `EXELY_IP_WHITELIST` (Exely IP rotation)
- `ATLAS_TIER` (M10 → M20 upgrade durumu)

---

## 3. Sorun → Triage Akışı

| Belirti                              | İlk bakılacak yer                            | Karar               |
| ------------------------------------ | -------------------------------------------- | ------------------- |
| Müşteri "site açılmıyor"             | §1 readiness + Sentry Last Seen              | 5xx >50% → ROLLBACK |
| HR booking gelmiyor                  | `/api/observability/health` + CM breaker pill | CB OPEN → §4.HR    |
| Outbox FAIL Sentry alert             | `cm_backlog_alert --json`                    | reasons → §4.Outbox |
| Sampler error (DBA queue)            | Mongo health endpoint                        | Atlas console       |
| 401/403 spike                        | JWT_SECRET değişti mi? Workflow restart      | secret panel        |
| ChunkLoadError surge (frontend)      | Yeni deploy oldu mu? Cache invalidate gerek  | hard-refresh prompt |
| Ödeme webhook'ları kaybolmuş         | `/api/health` + outbox `pending` count       | retry processor     |
| QuickID 503                          | Quick-ID API workflow log                    | restart + KVKK alert|
| Sentry'de PII leak şüphesi           | Event'i aç, scrub pattern eksik mi tespit    | docs/SENTRY...md §5 |

**Karar matrisi (5 dakikalık kural):**
1. Müşteri verisi risk altında mı? → **EVET → ROLLBACK** (sor sonra)
2. Bir özellik kapalı ama müşteri verisi güvenli mi? → **TRIAGE → log oku**
3. Sadece "yavaş" mı? → **GÖZLEMLE** + index audit

---

## 4. Yaygın Senaryo Çözümleri

### 4.HR — HotelRunner sync FAIL / CB OPEN

```bash
# 1. Hangi connection'da CB açık?
curl -fsS -H "Authorization: Bearer $ADMIN_JWT" \
  https://<prod-domain>/api/channel-manager/unified-rate-manager/circuit-breakers | jq

# 2. Reset (provider düzeldi mi emin olduktan sonra)
# Sadece kod tarafından — UI: "Reset breaker" butonu

# 3. Manuel pull (sync_scheduler tek seferlik)
# UI: Channel Manager → Sync Now butonu (3 retry ile)
```

**Eskalasyon:** 3+ provider OPEN ise → on-call (PagerDuty)

### 4.Outbox — backlog FAIL

```bash
# 1. Mevcut durum
python backend/scripts/cm_backlog_alert.py --json | jq

# 2. Failed olanları gözden geçir (DB read-only — code_execution)
# checkDatabase environment=production query="SELECT count(*) ... FROM cm_outbox WHERE status='failed'"

# 3. Outbox dispatcher worker restart (Backend API workflow restart yeterli)
```

**Eskalasyon:** `oldest_seconds >= 1800s` (30 dk birikmiş) → on-call

### 4.Backup — Atlas snapshot stale

```bash
# Snapshot tazelik (API key varsa)
python backend/scripts/verify_atlas_backup.py --max-age-hours 26

# Atlas console: cloud.mongodb.com → Cluster → Backup
# Continuous backup açık mı? PITR window aktif mi?
```

**Eskalasyon:** Snapshot >36 saat eski → DBA (PagerDuty `pms-pilot-dba`)

### 4.Rollback — kod hatası post-deploy

```bash
# Sıralı:
bash deploy/rollback.sh --list      # mevcut tag'leri gör
bash deploy/rollback.sh --dry-run   # ne olacak gör
bash deploy/rollback.sh             # uygula (smoke otomatik koşar)

# Smoke FAIL ederse .rollback_from sidecar dosyası bırakır
cat deploy/.rollback_from           # manuel inceleme için
```

**Detay:** `docs/ROLLBACK.md` — 4 senaryo

### 4.PII — Sentry'de hassas veri sızıntısı şüphesi

1. Sentry-UI → Issues → şüpheli event'i aç
2. Tüm alanları tara: message, breadcrumbs, extra, tags
3. `<JWT>`, `<EMAIL>`, `1.2.x.4`, `<OID>`, `<TOKEN>`, `<REDACTED>` görmüyorsan → scrub pattern eksik
4. `backend/infra/cloud_observability.py:28-40` `_PII_PATTERNS` listesine pattern ekle
5. Backend API workflow restart
6. Test event ile doğrula (`docs/SENTRY_ALERT_POLICY.md` §5)

---

## 5. Eskalasyon

| Severity | Kanal                       | Kim                |
| -------- | --------------------------- | ------------------ |
| CRITICAL | PagerDuty + #pms-incidents  | On-call rotation   |
| ERROR    | #pms-alerts + email         | Mesai içi: dev team |
| WARNING  | #pms-alerts (digest)        | Sabah review       |
| DBA      | PagerDuty `pms-pilot-dba`   | DBA on-call        |

**Müşteri iletişimi**: status-page.syroce.com (varsa) güncelle —
müşteri PMS'siz kalırsa 5dk içinde duyuru.

---

## 6. Komut Hızlı Referansı (alfabetik)

```bash
# Backup tazelik kontrolü
python backend/scripts/verify_atlas_backup.py --max-age-hours 26

# CM backlog + breaker durumu
python backend/scripts/cm_backlog_alert.py [--json] [--quiet] [--sentry-capture]

# Exely IP whitelist doğrulama
python backend/scripts/verify_exely_whitelist.py --env production --expect-ips "..."

# Index audit (yavaşlık)
python backend/scripts/index_audit.py
python backend/scripts/index_apply.py

# Readiness (HTTP)
curl -fsS https://<prod-domain>/api/production-golive/readiness | jq

# Rollback
bash deploy/rollback.sh --list
bash deploy/rollback.sh --dry-run
bash deploy/rollback.sh [tag]

# Smoke (deploy/rollback sonrası otomatik koşar; manuel:)
bash deploy/smoke.sh
```

---

## 7. İlgili Dokümanlar

| Konu                          | Doküman                                |
| ----------------------------- | -------------------------------------- |
| Rollback senaryoları (4)      | `docs/ROLLBACK.md`                     |
| Atlas backup + restore        | `docs/ATLAS_BACKUP_AND_RESTORE.md`     |
| CM observability eşikleri     | `docs/CM_OBSERVABILITY.md`             |
| Sentry alert policy           | `docs/SENTRY_ALERT_POLICY.md`          |
| Pilot Go/No-Go                | `docs/PILOT_GO_NO_GO.md`               |
| HR pilot template             | `docs/PILOT_GO_NO_GO_HR_TEMPLATE.md`   |
| Production safety plan        | `docs/PRODUCTION_SAFETY_PLAN.md`       |
| Disaster recovery (full)      | `docs/DISASTER_RECOVERY.md`            |
| Incident playbook (full)      | `docs/INCIDENT_PLAYBOOK.md`            |

---

## 8. Replit-Spesifik Notlar

- **Workflow restart**: Workspace → Workflows panel → workflow seç → "Restart"
- **Secret düzenleme**: Sağ panel → Secrets → vault GUI (terminal'e ASLA yazma)
- **Log tail**: `/tmp/logs/<workflow_name>_*.log` (auto-rotated)
- **Shell**: workspace shell zaten `/home/runner/workspace` (cd gerekmez)
- **Preview**: iframe proxy (mTLS) — `https://<port>-<dev-domain>` formatı
- **Production**: `.replit.app` veya custom domain (post-publish)
- **Code execution sandbox** (Agent only): `database`, `query-integration-data`,
  `web-search` skill'leri için — operatör bunları kullanmaz, agent kullanır

---

## 9. Sürüm

- **v1.0** (12 Mayıs 2026) — Pilot HR canlı CM öncesi ilk yayın
- **Maintainer**: Pilot operasyon ekibi
- **Geri besleme**: Eksik komut/senaryo varsa GitHub PR
