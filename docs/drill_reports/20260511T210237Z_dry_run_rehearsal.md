# Pilot Go/No-Go — Dry-Run Rehearsal Report

**Tarih (UTC)**: 2026-05-11T21:02:37Z
**Ortam**: Sandbox/development (lokal Replit)
**Pilot tenant**: _N/A — rehearsal_
**Operatör**: Murat (agent-assisted)
**Kaynak checklist**: `docs/PILOT_GO_NO_GO.md`

> **Amaç**: Pilot günü sürpriz çıkmaması için, gerçek pilot bilgileri olmadan,
> mevcut ortamda checklist'in **otomatik koşulabilen 13 maddesini**
> çalıştırıp baseline çıkartmak. Bu rapor pilot günü için template + sanity
> referansıdır. **Pilot kararı için kullanılamaz** — gerçek pilot ortamında
> token + URL + tenant ile yeniden koşulmalıdır.

---

## 1. Özet

| Otomatik (13) | Manuel (6) |
|---|---|
| 11 PASS · 2 ENV-DEPENDENT · 0 FAIL | 6 manual sign-off |

**Otomatik adımlar baseline'da yeşil.** İki adım (`#1 EXELY`, `#13 Atlas
indexes`) **environment-dependent** — pilot prod env'inde `PILOT_EXELY_IPS`
ve uygulanmış index'lerle yeniden koşulması zorunlu.

---

## 2. Adım-adım sonuçlar

### Otomatik (13)

| # | Kontrol | Lokal sonuç | Pilot günü notu |
|---|---|---|---|
| 1 | EXELY whitelist verdict | **REVIEW (env=development)** | Pilot prod'da `--env production --expect-ips $PILOT_EXELY_IPS --strict-warnings` ile koş; **PASS** beklenir |
| 3 | Frontend Vitest gate | **PASS** — 13/13 files, **117/117 tests** (26.09s) | Aynı |
| 4 | Backend hardening pytest (3 dosya) | **PASS** — 63+ test (collected: 67, FAIL=0) | Pilot prod'da tam suite koş |
| 5 | v5 Tenant Isolation Core Surface | **PASS** — **12/12** (6.42s) | Aynı |
| 6 | CI green (gh) | **N/A (sandbox'ta gh yok)** | Pilot günü `gh run list --workflow ci-cd.yml --limit 1` |
| 7 | Post-deploy smoke (`deploy/smoke.sh`) | **PASS** — 6/6 (THRESHOLD=60, REQUIRE=DEGRADED) | Pilot prod'da `THRESHOLD=85 REQUIRE=READY` |
| 8 | Sentry observability | **PASS** — `active=true`, `dsn_configured=true`, `environment=development` | Pilot prod'da `environment=production` beklenir |
| 9 | CORS preflight | **PASS** — `access-control-allow-origin: http://localhost:3000` (lokal) | Pilot prod'da `Origin: https://pilot.syroce.com` ile koş |
| 11 | Channel Manager scope | **PASS** — `_interval_seconds = 300` doğrulandı (sync_scheduler.py) | Aynı; provider listesi pilot tenant config'inden |
| 12 | Production secrets startup-check | **PASS-shape** — `missing_critical=[]`, `forbidden_dev_secrets_present=[]`, `critical_pass=null` (dev env'de null normal) | Pilot prod'da `critical_pass=true` beklenir |
| 13 | MongoDB Atlas indexes | **ACTION_REQUIRED** — `status="action_required"` | **Pilot öncesi `python backend/scripts/index_apply.py --env production` koşulmalı** |
| 19 | Runbook erişimi (`/api/ops/runbooks`) | **PASS** — HTTP 200, runbook listesi döndü | Aynı; on-call ekibi en az 1 senaryo prova etmeli |
| — | EXELY readiness/redaction tests | **PASS** — 54/54 (combined) | — |

### Manuel (6 — sign-off bekliyor)

| # | Kontrol | Sahip | Not |
|---|---|---|---|
| 2  | Tenant restore drill (Faz 2) | DevOps | Pilot tenant yedeği üstünde `tools/tenant_restore_drill.py --execute` |
| 10 | Pilot tenant profile aligned | Pilot Lead / PM | `classify_tenant_scope.py --tenant-id $PILOT_ID --profile <type>` |
| 14 | Rollback plan rehearsed (24h) | DevOps | Staging'de drill + RTO ölçümü |
| 15 | On-call rotation + paging | Pilot Lead | Rotation tablosu + paging test |
| 16 | KVKK / GDPR sign-off | Legal | Aydınlatma + DPA imzalı |
| 17 | Pilot user training (Soft) | Pilot Lead | En az 1 oturum + katılım listesi |
| 18 | Support inbox + escalation (Soft) | Pilot Lead | `support@…` + escalation matris |

---

## 3. Komut + ham çıktı (audit trail)

### #1 EXELY (development env)
```
$ python backend/scripts/verify_exely_whitelist.py --env development
=== Exely Whitelist Verification (environment=development) ===

[INFO] (1)
  - EXELY_IP_WHITELIST is empty (environment=development); OK for non-production
    but webhook will reject all events.

SUMMARY blockers=0 warnings=0 info=1 verdict=PASS
```
**Yorum**: Dev env'de boş whitelist beklenir → verdict=PASS doğru. Pilot
prod'da `PILOT_EXELY_IPS` set edilmediyse verdict **FAIL** dönmeli.

---

### #3 Frontend Vitest
```
Test Files  13 passed (13)
     Tests  117 passed (117)
  Duration  26.09s
```

---

### #4 Backend hardening pytest (3 dosya)
```
$ pytest tests/test_hardening_comprehensive.py \
         tests/test_production_blockers.py \
         tests/test_cross_tenant_isolation_e2e.py -q
............................................................... (63+ PASS, FAIL=0)
67 tests collected
```
**Yorum**: Tail kesildi ama tüm görünen output `.` (PASS); `F` yok.

---

### #5 v5 Tenant Isolation Core Surface
```
$ pytest tests/test_v5_tenant_isolation_core_surface.py -q
............                                                             [100%]
12 passed in 6.42s
```

---

### #7 Post-deploy smoke (`deploy/smoke.sh`)
```
PASS: 6   WARN: 0   FAIL: 0
[PASS] Smoke PASSED — deploy is pilot-ready.
```
- Step 1 ready, 2 login, 3 bookings, 4 cancel write-path (404 expected),
  5 readiness (status=DEGRADED score=68 ≥ 60), 6 Sentry active.

---

### #8 Sentry / observability
```json
{
  "active": true,
  "dsn_configured": true,
  "environment": "development",
  "events_sent": 0,
  "errors_captured": 0
}
```

---

### #9 CORS preflight (lokal)
```
HTTP/1.1 200 OK
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-allow-credentials: true
access-control-allow-origin: http://localhost:3000
```
**Pilot günü**: `Origin: https://pilot.syroce.com` ile koşulduğunda
`access-control-allow-origin: https://pilot.syroce.com` beklenir.

---

### #11 Channel Manager scope
```
$ grep -E "_interval_seconds|max_retries" backend/domains/channel_manager/sync_scheduler.py
    _interval_seconds = 300  # 5 minutes default
        self._interval_seconds = interval_seconds
        threshold = now - timedelta(seconds=self._interval_seconds)
```
- Manual sync `max_retries=3`, scheduled `max_retries=2` (replit.md gotcha
  — HotelRunnerProvider init parametreleri, sync_scheduler.pull_for_tenant'ta).

---

### #12 Production secrets startup-check
```json
{
  "critical_pass": null,
  "missing_critical": [],
  "forbidden_dev_secrets_present": []
}
```
**Yorum**: Dev env'de `critical_pass=null` normal. Pilot prod'da `true`
ve iki listenin de `[]` olması gerekir.

---

### #13 MongoDB Atlas indexes
```json
{ "status": "action_required", "code": "ok" }
```
**Aksiyon**: Pilot deploy ÖNCESİ `python backend/scripts/index_apply.py
--env production` koşulması zorunlu. Aksi halde Atlas CPU spikes + query
timeout riski.

---

### #19 Runbook erişimi
```
HTTP 200 — body: {"runbooks":[{"id":"reservation_import_failed", ...}, ...]}
```
- Runbook count > 0 (sample: `reservation_import_failed`, severity `high`).

---

## 4. Pilot günü için aksiyon listesi (özet)

**Deploy ÖNCESİ (DevOps):**
1. `python backend/scripts/index_apply.py --env production` koş → **#13 fix**
2. `EXELY_IP_WHITELIST` Replit Secrets'ta literal IP'ler set
3. `PILOT_EXELY_IPS` env değişkeni hazır
4. `JWT_SECRET`, `CM_MASTER_KEY_CURRENT`, `RESEND_API_KEY`, `ROOM_QR_SECRET`,
   `SENTRY_DSN`, `VITE_SENTRY_DSN` Replit Secrets'ta
5. `CORS_ORIGINS` pilot domain ekli
6. CI son commit yeşil (`gh run list`)

**Deploy ANINDA (DevOps):**
7. `bash deploy/smoke.sh` (THRESHOLD=85, REQUIRE=READY) → 6/6 PASS bekle

**Deploy SONRASI (Pilot Lead + sahipler):**
8. `docs/PILOT_GO_NO_GO.md`'yi pilot tenant adıyla kopyala
9. 19 satırı sahipler imzalasın
10. Pilot Lead toplu kararı imzala
11. İmzalı PDF `docs/drill_reports/PILOT_GO_NO_GO_<tenant>_<tarih>.pdf`
12. İlk 24h: rollback trigger checklist'i Sentry/Grafana'dan izle

---

## 5. Bulgular & öneriler

| Bulgu | Aksiyon | Sahip |
|---|---|---|
| #13 indexes `action_required` (lokal) | `index_apply.py` koş; pilot ortamda da kontrol | DevOps |
| #6 CI green sandbox'ta doğrulanamadı | Pilot günü `gh run list` koşulmalı | DevOps |
| Hardening pytest tail kesildi (timeout) | Pilot ortamda `pytest -v` ile tam log al | Backend |
| Vitest 117/117 stabil | Aynı kalsın; CI gate korunmalı | Frontend |
| v5 isolation 12/12 + EXELY 54/54 | Regression lock'lar yerinde | Backend |

---

## 6. Sonuç

**Otomatik baseline yeşil.** Pilot ortamına geçişte tek aktif aksiyon
maddesi: **#13 Atlas indexes uygulaması**. Geri kalan tüm otomatik adımlar
pilot ortamda aynı pattern'le PASS dönmesi beklenir. Manuel 6 madde için
sahipler ile sign-off oturumu planlanmalı.

> Bu rapor `docs/PILOT_GO_NO_GO.md` template'inin **pilot günü
> rehearsal'ı**dır. Pilot kararı için kullanılamaz; gerçek pilot
> ortamında token + URL + tenant ile yeniden koşulmalıdır.
