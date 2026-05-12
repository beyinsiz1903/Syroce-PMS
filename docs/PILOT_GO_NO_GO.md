# Syroce PMS — Pilot Go / No-Go Final Checklist

> **Amaç**: Pilot trafiğini açmadan önce tüm kritik kapıların geçildiğini tek
> belgede toplamak. Her satır bir **owner** tarafından **verification command**
> ile doğrulanır, **expected output** ile karşılaştırılır, **PASS / FAIL / N/A**
> işaretlenir ve **sign-off** alınır.
>
> **Karar kuralı**: Tüm `Hard` satırlar **PASS** olmadan pilot trafiği AÇILMAZ.
> Bir `Soft` satır FAIL ise **Pilot Lead** kararıyla devam edilebilir (notlara
> gerekçe yazılır).

---

## 1. Özet Tablo (one-page view)

| #  | Kategori     | Kontrol                                       | Owner             | Tip   | Status | Sign-off | Tarih |
|----|--------------|-----------------------------------------------|-------------------|-------|--------|----------|-------|
| 1  | Security     | EXELY whitelist verdict                       | DevOps            | Hard  | ☐      |          |       |
| 2  | Infra        | Tenant restore drill (Faz 2)                  | DevOps            | Hard  | ☐      |          |       |
| 3  | Tests        | Frontend Vitest gate                          | Frontend          | Hard  | ☐      |          |       |
| 4  | Tests        | Backend hardening + isolation pytest          | Backend           | Hard  | ☐      |          |       |
| 5  | Tests        | v5 Tenant Isolation Core Surface (12 test)    | Backend           | Hard  | ☐      |          |       |
| 6  | Infra        | CI green (ci-cd + frontend-quality)           | DevOps            | Hard  | ☐      |          |       |
| 7  | Infra        | Post-deploy smoke (deploy/smoke.sh 6/6)       | DevOps            | Hard  | ☐      |          |       |
| 8  | Integration  | Sentry / observability active                 | DevOps            | Hard  | ☐      |          |       |
| 9  | Security     | CORS pilot domain whitelisted                 | DevOps            | Hard  | ☐      |          |       |
| 10 | Config       | Pilot tenant profile aligned                  | Pilot Lead / PM   | Hard  | ☐      |          |       |
| 11 | Integration  | Channel Manager scope (Exely + HotelRunner)   | Backend (CM)      | Hard  | ☐      |          |       |
| 12 | Security     | Production secrets startup-check              | DevOps            | Hard  | ☐      |          |       |
| 13 | Infra        | MongoDB Atlas indexes ready                   | DevOps            | Hard  | ☐      |          |       |
| 14 | Ops          | Rollback plan rehearsed (last 24h)            | DevOps            | Hard  | ☐      |          |       |
| 15 | Ops          | On-call rotation + paging configured          | Pilot Lead        | Hard  | ☐      |          |       |
| 16 | Security     | KVKK / GDPR data-handling sign-off            | Legal / Pilot Lead| Hard  | ☐      |          |       |
| 17 | Ops          | Pilot user training delivered + acknowledged  | Pilot Lead        | Soft  | ☐      |          |       |
| 18 | Ops          | Support inbox + escalation matrix live        | Pilot Lead        | Soft  | ☐      |          |       |
| 19 | Ops          | Runbook erişimi (`/api/ops/runbooks` 200)     | Pilot Lead        | Soft  | ☐      |          |       |

> **Sign-off kuralı**: Her satırı **kendi owner'ı** imzalar (sadece Pilot Lead
> değil — accountability dağıtık). Pilot Lead son satırda toplu kararı imzalar.

**Karar (Pilot Lead imzası):** ☐ GO  ☐ NO-GO  ☐ DELAY

> Pilot Lead: __________________________  Tarih: ____________  İmza: __________

---

## 2. Detaylar (verification + expected output)

### #1 — EXELY whitelist verdict  ·  Security · Hard · DevOps

**Neden**: Exely webhook literal IP match yapıyor (CIDR desteklemiyor). Yanlış
config 503 döner ve pilot OTA sync ölür.

**Verification**:
```bash
python backend/scripts/verify_exely_whitelist.py \
  --env production \
  --expect-ips "$PILOT_EXELY_IPS" \
  --strict-warnings
```

**Expected output** (son satır):
```
SUMMARY blockers=0 warnings=0 info=2 verdict=PASS
```

**Notes**:
- IP'ler raporda redaksiyonlu (`1.2.3.4` → `1.2.x.4`).
- 54 test kapsam altında (`test_verify_exely_whitelist.py` + `test_readiness_validator_exely_check.py`).
- Aynı `verify()` `infra/readiness_validator.py` 9. alt-check + `server.py` startup audit'ine wired.

---

### #2 — Tenant restore drill (Faz 2)  ·  Infra · Hard · DevOps

**Neden**: Pilot tenant'ın yedeğinden tek-tenant restore mümkün ve diğer
tenant'lara sızıntı yok mu — felaket durumu gerekliliği.

**Verification**:
```bash
python tools/tenant_restore_drill.py \
  --backup-archive "$ARCHIVE_PATH" \
  --tenant-id "$PILOT_ID" \
  --target-db drill_staging \
  --execute
```

**Expected output**:
```
Verification: pass (leak_count=0, fk_orphan_count=0)
Drill report written to docs/drill_reports/<timestamp>_<tenant>_drill.md
```

**Notes**:
- `leak_count=0` → diğer tenant verisi sızmamış.
- `fk_orphan_count=0` → referans bütünlüğü korunmuş.
- Drill raporu PR'a iliştirilir.

---

### #3 — Frontend Vitest gate  ·  Tests · Hard · Frontend

**Verification**:
```bash
cd frontend && yarn test
```

**Expected output**:
```
Test Files  13 passed (13)
Tests       117 passed (117)
```

**Notes**:
- `.github/workflows/frontend-quality.yml` içinde hard gate.
- Tek bir test FAIL ise pilot bloklanır.

---

### #4 — Backend hardening + isolation pytest  ·  Tests · Hard · Backend

**Verification**:
```bash
cd backend && pytest \
  tests/test_hardening_comprehensive.py \
  tests/test_production_blockers.py \
  tests/test_cross_tenant_isolation_e2e.py \
  -v
```

**Expected output**:
```
====== 19 passed in <Xs> ======
```

---

### #5 — v5 Tenant Isolation Core Surface  ·  Tests · Hard · Backend

**Neden**: 6 yüzey × 2 attack vector cross-tenant penetration testi. Service
katmanı body/path tenant_id'ye göre değil, authenticated user tenant_id'sine
göre çağrılmalı.

**Verification**:
```bash
cd backend && pytest tests/test_v5_tenant_isolation_core_surface.py -v
```

**Expected output**:
```
====== 12 passed in 3.26s ======
```

**Notes**:
- Yüzeyler: folio payment, check-in, check-out, night audit, tenant-users, granted-permissions.
- 404-not-403 information disclosure protection pin'li.

---

### #6 — CI green  ·  Infra · Hard · DevOps

**Verification**:
```bash
gh run list --workflow ci-cd.yml          --limit 1 --json conclusion -q '.[0].conclusion'
gh run list --workflow frontend-quality.yml --limit 1 --json conclusion -q '.[0].conclusion'
```

**Expected output**:
```
success
success
```

**Notes**:
- En son main commit'i için iki workflow da yeşil olmalı.
- Cancelled/failure → pilot bloklanır.

---

### #7 — Post-deploy smoke  ·  Infra · Hard · DevOps

**Verification**:
```bash
BASE_URL=https://pilot-api.syroce.com \
ADMIN_EMAIL="$PILOT_ADMIN_EMAIL" \
ADMIN_PASSWORD="$PILOT_ADMIN_PASS" \
READINESS_THRESHOLD=85 \
bash deploy/smoke.sh
```

**Expected output** (son satırlar):
```
PASS: 6   WARN: 0   FAIL: 0
[PASS] Smoke PASSED — deploy is pilot-ready.
```

**Notes**:
- 6 adım: ready / login / bookings / cancel write-path / readiness / Sentry.
- Detay: `deploy/SMOKE.md`.
- `ENABLE_STRICT_SMOKE=1` ile rehearsal'da WARN → FAIL.

---

### #8 — Sentry / observability active  ·  Integration · Hard · DevOps

**Verification**:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://pilot-api.syroce.com/api/production-golive/summary \
  | jq '.observability.sentry'
```

**Expected output**:
```json
{
  "active": true,
  "dsn_configured": true,
  "environment": "production"
}
```

**Notes**:
- Backend: `SENTRY_DSN` Replit Secrets'ta.
- Frontend: `VITE_SENTRY_DSN` build-time set.
- Smoke step 6 ile çakışıyor — orada PASS ise burası da PASS.

---

### #9 — CORS pilot domain whitelisted  ·  Security · Hard · DevOps

**Verification**:
```bash
curl -I -X OPTIONS \
  -H "Origin: https://pilot.syroce.com" \
  -H "Access-Control-Request-Method: GET" \
  https://pilot-api.syroce.com/api/health
```

**Expected output**:
```
HTTP/1.1 204 No Content
access-control-allow-origin: https://pilot.syroce.com
```

**Notes**:
- `CORS_ORIGINS` `.replit`'te / production secret'larda.
- Wildcard `*` pilot için **kabul edilemez** — explicit domain.

---

### #10 — Pilot tenant profile aligned  ·  Config · Hard · Pilot Lead / PM

**Verification**:
```bash
python backend/scripts/classify_tenant_scope.py \
  --tenant-id "$PILOT_ID" \
  --profile BOUTIQUE_HOTEL
```

**Expected output**:
```
Tenant profile aligned: BOUTIQUE_HOTEL
Modules ACTIVE: pms, channel_manager, housekeeping, night_audit
```

**Notes**:
- Property type seçimi pilot tenant'ın mülk tipiyle eşleşmeli.
- Yanlış profile → kullanıcı yanlış modülleri görür.

---

### #11 — Channel Manager scope  ·  Integration · Hard · Backend (CM)

**Verification**:
```bash
grep -E "_interval_seconds|max_retries" \
  backend/domains/channel_manager/sync_scheduler.py
```

**Expected output**:
```
_interval_seconds = 300   # 5 min
HotelRunnerProvider(max_retries=3)   # manual
HotelRunnerProvider(max_retries=2)   # scheduled
```

**Notes**:
- Manual sync 3 retry, scheduled 2 retry (replit.md gotcha).
- Pilot'ta hangi provider'lar aktif: ☐ Exely  ☐ HotelRunner  ☐ Diğer: ____

---

### #12 — Production secrets startup-check  ·  Security · Hard · DevOps

**Verification**:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://pilot-api.syroce.com/api/production-golive/config/startup-check \
  | jq '{critical_pass, missing_critical, forbidden_dev_secrets_present}'
```

**Expected output** (gerçek shape `infra/production_config.py:441-443`):
```json
{
  "critical_pass": true,
  "missing_critical": [],
  "forbidden_dev_secrets_present": []
}
```

**Notes**:
- `JWT_SECRET`, `CM_MASTER_KEY_CURRENT`, `RESEND_API_KEY`, `ROOM_QR_SECRET` Replit Secrets'ta.
- `.replit`'te açıkta hardcoded değer → boot blocker.
- Pilot komutunda `jq '{critical_pass, missing_critical, forbidden_dev_secrets_present}'`.

---

### #13 — MongoDB Atlas indexes ready  ·  Infra · Hard · DevOps

**Verification**:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://pilot-api.syroce.com/api/production-golive/mongo/indexes \
  | jq '.status'
```

**Expected output**:
```
"READY"
```

**Notes**:
- `python backend/scripts/index_apply.py --env production` ile uygulanır.
- Eksik index → query timeout / Atlas CPU yükü.
- Atlas 500-collection limiti hatırlatması: yeni koleksiyon ekleme yok (discriminator pattern).

---

### #14 — Rollback plan rehearsed  ·  Ops · Hard · DevOps

**Verification** (manuel):
- Son 24 saatte staging'de rollback drill yapıldı.
- `bash deploy/rollback.sh` veya Replit checkpoint restore süresi <5 dk (detay: `docs/ROLLBACK.md`).
- DB rollback adımı doküman olarak hazır (`deploy/DEPLOYMENT_GUIDE.md`).

**Expected**:
- Drill timestamp + sorumlu kişi + RTO ölçümü notlanmış.

---

### #15 — On-call rotation + paging  ·  Ops · Hard · Pilot Lead

**Verification** (manuel):
- Pilot süresince 24/7 on-call rotation tanımlı.
- Paging kanalı (Slack / SMS / phone) test edildi.
- Escalation L1 → L2 → CTO tanımlı.

**Expected**:
- Rotation tablosu + paging test timestamp'i kayıt altında.

---

### #16 — KVKK / GDPR sign-off  ·  Security · Hard · Legal / Pilot Lead

**Verification** (manuel):
- Pilot tenant ile KVKK Aydınlatma Metni + DPA imzalı.
- Quick-ID flow'unda ID foto retention politikası onaylı.
- Veri ihlali bildirim süresi (72 saat) için runbook hazır.

**Expected**:
- İmzalı belgeler dosyalandı; referans no notlandı.

---

### #17 — Pilot user training  ·  Ops · Soft · Pilot Lead

**Verification** (manuel):
- En az 1 oturum verildi (front desk + housekeeping + finance).
- Katılım listesi alındı, kullanıcılar in-app help'i biliyor.

---

### #18 — Support inbox + escalation matrix live  ·  Ops · Soft · Pilot Lead

**Verification** (manuel):
- `support@…` veya in-app feedback aktif.
- Escalation matris (kim hangi kategoriye bakar) yayında.

---

### #19 — Runbook erişimi  ·  Ops · Soft · Pilot Lead

**Neden**: Pilot incident'te `backend/controlplane/runbooks.py` (15 runbook)
on-call için tek bakışta erişilebilir olmalı.

**Verification**:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://pilot-api.syroce.com/api/ops/runbooks | jq 'length'
```

**Expected output**:
```
15
```

**Notes**: On-call ekibi en az 1 senaryo (örn. "Atlas yavaşlığı") runbook'unu
prova etmiş olmalı.

---

## 3. Hızlı koşum (one-shot dry-run)

Hard adımların büyük kısmı tek oturumda otomatik koşulabilir:

```bash
# 1. EXELY
python backend/scripts/verify_exely_whitelist.py --env production \
  --expect-ips "$PILOT_EXELY_IPS" --strict-warnings

# 3+4+5. Tests
cd frontend && yarn test && cd ..
cd backend && pytest \
  tests/test_hardening_comprehensive.py \
  tests/test_production_blockers.py \
  tests/test_cross_tenant_isolation_e2e.py \
  tests/test_v5_tenant_isolation_core_surface.py -v && cd ..

# 7. Smoke
BASE_URL=https://pilot-api.syroce.com \
  READINESS_THRESHOLD=85 \
  bash deploy/smoke.sh
```

İkinci tur (deploy sonrası, prod token gerekli):

```bash
TOKEN=$(curl -s -X POST https://pilot-api.syroce.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$PILOT_ADMIN_EMAIL\",\"password\":\"$PILOT_ADMIN_PASS\"}" \
  | jq -r .access_token)

# 8. Sentry
curl -s -H "Authorization: Bearer $TOKEN" \
  https://pilot-api.syroce.com/api/production-golive/summary \
  | jq '.observability.sentry'

# 9. CORS
curl -I -X OPTIONS -H "Origin: https://pilot.syroce.com" \
  -H "Access-Control-Request-Method: GET" \
  https://pilot-api.syroce.com/api/health

# 12. Secrets
curl -s -H "Authorization: Bearer $TOKEN" \
  https://pilot-api.syroce.com/api/production-golive/config/startup-check \
  | jq '{critical_pass, missing_critical, forbidden_dev_secrets_present}'

# 13. Indexes
curl -s -H "Authorization: Bearer $TOKEN" \
  https://pilot-api.syroce.com/api/production-golive/mongo/indexes | jq '.status'
```

---

## 4. Karar matrisi

| Hard FAIL sayısı | Soft FAIL sayısı | Karar           |
|------------------|------------------|-----------------|
| 0                | 0                | **GO**          |
| 0                | ≥1               | GO (Pilot Lead notu zorunlu) |
| ≥1               | herhangi         | **NO-GO** veya DELAY |

**Pilot Lead son imza:**

```
GO     ☐
NO-GO  ☐
DELAY  ☐  (yeni hedef tarih: __________)

İmza: __________________   Tarih: __________   Saat: __________
```

---

## 5. Rollback trigger checklist (ilk 24 saat post-go-live)

Pilot trafiği açıldıktan sonra **derhal rollback** tetikleyici eşikleri:

| Sinyal                                                     | Eşik (10 dk pencere) | Aksiyon                  |
|------------------------------------------------------------|----------------------|--------------------------|
| HTTP 5xx oranı                                             | ≥ %5                 | Otomatik rollback başlat |
| `/health/ready` 503                                        | ≥ 3 ardışık          | Rollback + DB inceleme   |
| Cross-tenant veri sızıntısı (Sentry tag `tenant_leak`)     | ≥ 1                  | **Rollback + acil incident** |
| Login başarı oranı düşüşü                                  | < %95                | İnceleme; auth/JWT kontrol |
| Atlas connection pool tükenmesi                            | %90+                 | Rollback + Atlas tier yükselt |
| Exely/HotelRunner sync error rate                          | ≥ %20                | CM'i pas geç, manuel mod |
| Response p95 latency                                       | > 3s                 | İnceleme; gerekirse rollback |
| Sentry yeni `ERROR` rate                                   | ≥ 10/dk              | İnceleme; tetikleyiciye göre rollback |

**Rollback komutu**:
```bash
bash deploy/rollback.sh            # tek komut — last_good_tag'e döner + smoke koşar
                                   # detay: docs/ROLLBACK.md
```

**RTO hedefi**: < 5 dk (rollback başlat → trafik eski versiyona dönsün).

**Post-rollback zorunlu**:
1. Incident kanalında bildirim
2. `docs/drill_reports/<timestamp>_pilot_rollback.md` doldur
3. KVKK 72-saat eşiği başladıysa Legal'e haber ver

---

## 6. Referanslar

- `docs/PILOT_READINESS_CHECKLIST.md` — operasyonel detay + hard-blocker tarihçesi
- `deploy/SMOKE.md` — post-deploy 6 adımlı smoke runbook
- `deploy/DEPLOYMENT_GUIDE.md` — deploy + rollback adımları
- `replit.md` — gotcha'lar (EXELY format, JWT lifespan, Atlas 500-collection limiti, vb.)
- `backend/scripts/verify_exely_whitelist.py` — EXELY verdict modeli (`--help`)
- `backend/infra/readiness_validator.py` — 9 alt-check, score 0-100
- `tools/tenant_restore_drill.py` — Faz 2 restore drill

---

> Bu belge **canlı doküman**. Her pilot turu için kopyala (`PILOT_GO_NO_GO_<tenant>_<tarih>.md`),
> imzalı PDF'ini `docs/drill_reports/` altına arşivle.
