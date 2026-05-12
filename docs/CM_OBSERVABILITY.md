# CM Observability — Outbox + Circuit Breaker Alarm Playbook

Single source of truth for CM/outbox visibility during the HR pilot.
Threshold logic lives in `backend/infra/cm_observability_check.py`;
the readiness API, the cron alarm, and the dashboard pill banner all
import from it so a tuning change is one-place.

---

## Sinyal yüzeyleri (3 yer, hepsi aynı kaynaktan)

| Yüzey                                                         | Hedef                       | Erişim                              |
| ------------------------------------------------------------- | --------------------------- | ----------------------------------- |
| `GET /api/health/readiness` → `checks.cm_outbox` + `cm_circuit_breakers` | Pilot panel + CI deploy gate | Public (IP + tenant scrub edilmiş)  |
| `python backend/scripts/cm_backlog_alert.py [--json]`          | Cron → Sentry monitor       | Server-side cron / sentry-cli       |
| `GET /api/channel-manager/unified-rate-manager/circuit-breakers` | Operatör drill-down        | RBAC `view_system_diagnostics`      |

---

## Eşikler (defaults, tek-yer-değiştir: `cm_observability_check.py`)

### Outbox
| Metrik                            | DEGRADED | FAIL  | Score (DEGRADED / FAIL)  |
| --------------------------------- | -------- | ----- | ------------------------ |
| `pending + retry` (backlog)       | ≥ 100    | ≥ 500 | 0.5 / 0.0                |
| `failed` (terminal)               | ≥ 50     | ≥ 200 | 0.5 / 0.0                |
| Oldest pending age (s)            | ≥ 600    | ≥ 1800| 0.5 / 0.0                |
| No throughput while backlog>0 (s) | ≥ 1800   | —     | 0.5 / —                  |

### Circuit breakers (in-process `provider_failover._breakers`)
| Open count | Verdict   | Score |
| ---------- | --------- | ----- |
| 0          | OK        | 1.0   |
| 1–2        | DEGRADED  | 0.5   |
| ≥ 3        | FAIL      | 0.0   |

`HALF_OPEN` recovery probe state'i informational — score'a etki etmez.

---

## Cron kurulumu (önerilen — Sentry monitors)

```bash
# Her dakika
* * * * * /usr/bin/sentry-cli monitors run cm-backlog -- \
    python /app/backend/scripts/cm_backlog_alert.py --json --quiet
```

`exit 1` → Sentry monitor failure → on-call'a page.
`exit 2` → DBA kuyruğuna page (script ya da DB bozuk).

Sentry-cli yoksa düz cron + Replit secret-based webhook:

```bash
* * * * * python /app/backend/scripts/cm_backlog_alert.py --quiet || \
    curl -X POST -d "verdict=fail" "$ALERT_WEBHOOK_URL"
```

---

## DEGRADED senaryoları — operatör akışı

### A) `backlog ≥ 100` (workers slow / provider rate-limited)
1. `python backend/scripts/cm_backlog_alert.py --json` → reasons listesini al
2. `GET /api/outbox/status` → per-status + provider failures breakdown
3. Provider rate-limit ise: `bash deploy/rollback.sh --list` → henüz
   rollback'e gerek YOK; sadece worker scale-up tetikle
   (`docker compose -f deploy/docker-compose.production.yml up -d --scale worker=2`)
4. Backlog 30 dk içinde düşmüyorsa → DEGRADED → FAIL geçişine yakındır,
   on-call'a önden bildir

### B) `failed ≥ 50` (real upstream errors, transient değil)
1. `GET /api/outbox/events?status=failed&limit=20` → hata sebepleri
2. Tek provider mı? → o provider'ın circuit breaker'ı zaten OPEN
   olmalıydı → kontrol et
3. Çoklu provider → upstream incident, status sayfası kontrol
4. `POST /api/outbox/replay` → manuel replay (super-admin)

### C) `oldest ≥ 600s` (worker stuck / dead-letter)
1. `docker compose -f deploy/docker-compose.production.yml ps` → worker
   container ayakta mı?
2. Logs: `docker compose -f deploy/docker-compose.production.yml logs -f worker`
3. Worker yeniden başlat: `docker compose -f deploy/docker-compose.production.yml restart worker`

### D) `circuit_breakers.open ≥ 3` (multi-provider blackout — FAIL)
1. **Otomatik**: readiness FAIL → `auto_rollback_engine` zaten `outbox_backlog`
   trigger'ını çalıştırır; aksiyon `alert_and_pause` (canary durur)
2. Manuel: `GET /api/channel-manager/unified-rate-manager/circuit-breakers`
   → hangi conn'lar OPEN
3. Reset: `POST /api/channel-manager/providers/{provider}/reset-circuit`
   (super-admin) — ama önce kök sebebi bul (rate limit / DNS / token)

---

## Privacy guarantee

Hiçbir yüzey (readiness JSON, cron stdout, Sentry monitor payload,
dashboard pill) şunları içermez:
- `tenant_id` veya tenant adı
- Connection ID / API token
- Olay payload'ları (booking_id'ler, guest data)
- Provider raw response body

Sadece counts + threshold reasons. Per-connection drill-down RBAC
arkasında (`/api/channel-manager/unified-rate-manager/circuit-breakers`).

---

## Test pinleri

- `backend/infra/cm_observability_check.py` import edilebilir, `db=None`
  ile çağrı `unknown` döner (asla raise etmez)
- `get_circuit_breaker_status()` `provider_failover._breakers` boş
  olsa bile `{"open": 0, "total": 0, "status": "ok", "score": 1.0}` döner
- `cm_backlog_alert.py --quiet` OK verdict'te stdout boş, exit 0
- Readiness JSON `cm_outbox.reasons` listesi DEGRADED/FAIL'de dolu olmalı
