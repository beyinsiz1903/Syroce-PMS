# Syroce PMS — Post-Deploy Smoke Test

Pilot Readiness checklist'in **hard-blocker #2** (DevOps) maddesini karşılayan
1 dakikalık post-deploy smoke. Deploy bittiği anda koşulur; PASS dönmezse
deploy reddedilir veya pilot ertelenir.

> **Tek komut:**
> ```bash
> BASE_URL=https://api.syroce.com bash deploy/smoke.sh
> ```

---

## Neyi kontrol eder

| # | Adım | Endpoint | Başarı koşulu | Tip |
|---|---|---|---|---|
| 1 | Liveness/Readiness | `GET /health/ready` | `HTTP 200` + `status=ready` (DB ping geçti) | **Hard** |
| 2 | Admin login | `POST /api/auth/login` | `HTTP 200` + `access_token` döner | **Hard** |
| 3 | Bookings read | `GET /api/pms/bookings?limit=1` | `HTTP 200` (tenant-scoped read path canlı) | **Hard** |
| 4 | Cancel write-path | `POST /api/pms-core/cancel` (bogus id) | `HTTP 400/404/422` (write router ulaşılır, scope reddediyor) | Soft\* |
| 5 | Production readiness | `GET /api/production-golive/readiness` | `status=READY` + `score ≥ THRESHOLD` | **Hard** |
| 6 | Sentry / observability | `GET /api/production-golive/summary` | `observability.sentry.active=true` | Soft\* |

\* Soft adım: WARN üretir, exit code'u etkilemez. `ENABLE_STRICT_SMOKE=1` ile
WARN da FAIL sayılır.

### Adım 4 neden bogus id?
Pilot-safe yaklaşım: gerçek bir rezervasyon yaratıp iptal etmek prod data'ya
dokunur. Var-olmayan bir `booking_id` ile `/cancel` çağırırsak:
- Router ulaşılır (5xx olmamalı),
- Auth + tenant scope geçer,
- Service katmanı 4xx (booking bulunamadı / invalid) döndürür.

Bu kombinasyon write-path'in canlı olduğunu kanıtlar **prod data mutasyonu olmadan**.

---

## Kullanım

### Standart pilot deploy

```bash
BASE_URL=https://api.syroce.com \
ADMIN_EMAIL=admin@syroce.com \
ADMIN_PASSWORD="$PILOT_ADMIN_PASS" \
READINESS_THRESHOLD=85 \
bash deploy/smoke.sh
```

### Pilot öncesi rehearsal (warn'ları da fail say)

```bash
ENABLE_STRICT_SMOKE=1 \
BASE_URL=https://staging.syroce.com \
bash deploy/smoke.sh
```

### Read-only smoke (yazma yüzeyini hiç sorgulama)

```bash
SKIP_WRITE_CHECKS=1 \
BASE_URL=https://api.syroce.com \
bash deploy/smoke.sh
```

### CI / cron entegrasyonu

```yaml
# .github/workflows/post-deploy-smoke.yml (örnek)
- name: Post-deploy smoke
  run: |
    BASE_URL=${{ secrets.PROD_BASE_URL }} \
    ADMIN_EMAIL=${{ secrets.SMOKE_ADMIN_EMAIL }} \
    ADMIN_PASSWORD=${{ secrets.SMOKE_ADMIN_PASS }} \
    READINESS_THRESHOLD=85 \
    bash deploy/smoke.sh
```

---

## Konfigürasyon (env değişkenleri)

| Değişken | Default | Açıklama |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Deploy hedefi (trailing slash auto-strip). |
| `ADMIN_EMAIL` | `demo@hotel.com` | Login için kullanıcı. |
| `ADMIN_PASSWORD` | `demo123` | Login parolası — **prod'da Replit Secrets'tan**. |
| `READINESS_THRESHOLD` | `70` | `overall_score ≥ X` koşulu (0-100). Pilot için 85 önerilir. |
| `READINESS_REQUIRE` | `READY` | İzin verilen statüler: `READY` / `DEGRADED` / `NOT_READY`. |
| `SKIP_WRITE_CHECKS` | `0` | `1` → adım 4'ü atla. |
| `READY_RETRIES` | `15` | `/health/ready` için deneme sayısı (her biri 2s). |
| `CURL_TIMEOUT` | `10` | Saniye, request başına. |
| `ENABLE_STRICT_SMOKE` | `0` | `1` → WARN da exit 1. |

---

## Exit kodları

| Code | Anlam | Aksiyon |
|---|---|---|
| `0` | Tüm hard adımlar PASS (warn olabilir) | Pilot devam |
| `1` | En az bir hard adım FAIL | **Deploy rollback / pilot ertele** |

Smoke tamamlanmadan pilot trafiği açılmamalı.

---

## Çıktı örneği — başarılı koşum

```
════════════════════════════════════════════════════════════
  Syroce PMS — Post-Deploy Smoke
  Target  : https://api.syroce.com
  Admin   : admin@syroce.com
  Score≥  : 85   Status= : READY
════════════════════════════════════════════════════════════

── Step 1/6 — Liveness/Readiness probe ──
[PASS] Ready (HTTP 200, status=ready) — attempt=1

── Step 2/6 — Admin login ──
[PASS] Login OK (token=eyJhbGc…X8w_)

── Step 3/6 — Bookings list (read-path + tenant scope) ──
[PASS] Bookings 200 (response type=array)

── Step 4/6 — Cancel write-path (deterministic 4xx on bogus id) ──
[PASS] Cancel write-path reachable (HTTP 400 — bogus id rejected, expected)

── Step 5/6 — /api/production-golive/readiness ──
[*] status=READY  score=92  threshold=85
[PASS] Readiness PASS (status=READY score=92 ≥ 85)

── Step 6/6 — Sentry / observability sanity ──
[PASS] Sentry active per /summary

════════════════════════════════════════════════════════════
  Smoke Verdict
════════════════════════════════════════════════════════════
  PASS: 6   WARN: 0   FAIL: 0
[PASS] Smoke PASSED — deploy is pilot-ready.
```

---

## Çıktı örneği — başarısız koşum

```
── Step 5/6 — /api/production-golive/readiness ──
[*] status=DEGRADED  score=62  threshold=85
[FAIL] Readiness FAIL — status=DEGRADED (need READY) score=62 (need ≥85)
    - exely_whitelist: FAIL
    - certificates: WARN

════════════════════════════════════════════════════════════
  Smoke Verdict
════════════════════════════════════════════════════════════
  PASS: 4   WARN: 1   FAIL: 1
[FAIL] Smoke FAILED — failed steps:
    • 5: readiness gate

Deploy MUST be rolled back or pilot postponed.
```

---

## Smoke fail olduğunda

1. **Adım 1 (readiness) FAIL** → DB veya boot sequence problemi. `/health/ready`
   response'unu incele (`status=db_unavailable` → Atlas; `status=starting` →
   bootstrap takıldı).
2. **Adım 2 (login) FAIL** → JWT_SECRET veya admin credential hatası.
   `replit.md` → `Production Secret Management` gotcha'sına bak.
3. **Adım 3 (bookings) FAIL** → tenant context veya routing problemi. Backend
   loglarında `domains.pms.bookings` traceback ara.
4. **Adım 4 (cancel write) 5xx** → write-path veya event bus hatası. Strict
   modda fail; default warn.
5. **Adım 5 (readiness) FAIL** → çıktıdaki ilk 5 sub-check incelenmeli.
   `exely_whitelist` FAIL ise → `python backend/scripts/verify_exely_whitelist.py
   --env production` ile detay (redacted).
6. **Adım 6 (Sentry) WARN** → `SENTRY_DSN` env yoksa veya SDK init başarısız.
   Manuel Sentry dashboard kontrolü yap.

---

## Bağımlılıklar

- `bash` 4+, `curl`, `jq`
- Read-only network erişimi `BASE_URL`'e

---

## Pilot Readiness sahibi

DevOps. Deploy sonrası 1 dakikalık koşum + sonuç loglanması zorunlu
(bkz. `docs/PILOT_READINESS_CHECKLIST.md` action #5).
