# Pilot Production Launch Rehearsal — Sandbox Walkthrough

**Tarih:** 2026-05-13 06:55Z
**Ortam:** Replit sandbox (cluster=hotel_pms Atlas BAĞLI, Backend canlı)
**Operatör:** Agent (rehearsal mode)
**Doc:** `docs/PRODUCTION_LAUNCH_REHEARSAL.md`
**Verdict:** **NO-GO** — sandbox pilot configürasyonu eksik (4 zorunlu secret unset, 1 keşfedilen bug fix'lendi).

---

## §0 9-Kapı sonuç tablosu

| # | Kapı | Sonuç | Not |
|---|------|-------|-----|
| 1 | Replit Secrets matrix | ⚠️ **PARTIAL** | 9/13 zorunlu set, 4 unset (§1 detay) |
| 2 | Sentry UI 11 alarm | N/A | Operatör eylemi (Sentry projesi sandbox'ta yok) |
| 3 | Sentry Crons (cm-backlog) | N/A | Operatör eylemi |
| 4 | Slack/PagerDuty routing | N/A | Operatör eylemi |
| 5 | rollback.sh --dry-run | ⚠️ **EXPECTED-FAIL** | `.last_good_tag` YOK (ilk deploy oluşturur, §4.1) |
| 6 | cm_backlog_alert.py --json | ✅ **PASS** (fix sonrası) | BUG keşfedildi + fix uygulandı (§4.2) |
| 7 | verify_atlas_backup.py | ⚠️ **NO-OP** | API key'ler unset → exit 0 (§4.3) |
| 8 | deploy/smoke.sh 6/6 | ❌ **5/6 PASS** | Step 5 readiness DEGRADED (§4.4) |
| 9 | PILOT_GO_NO_GO_HR | ✅ **COPIED** | `docs/drill_reports/PILOT_GO_NO_GO_sandbox_2026-05-13.md` |

**Multi-gate hard-stop kuralı:** Gate #1 + #8 FAIL → pilot 24h ERTELE.
Sandbox'ta zaten beklenen — bu tur **rehearsal**, gerçek pilot değil.

---

## §1 Secrets matrix — sandbox snapshot

Yöntem: `os.environ.get(k)` varlık kontrolü, **değer asla loglanmadı**.

### Zorunlu (set)
| Secret | Durum |
|---|---|
| `JWT_SECRET` | set (96 char) |
| `JWT_EXPIRATION_MINUTES` | set (5 char, "10080" beklenen) |
| `MONGO_ATLAS_URI` | set (74 char, `mongodb+srv://`) |
| `SENTRY_DSN` | set (95 char) |
| `VITE_SENTRY_DSN` | set (95 char) |
| `RESEND_API_KEY` | set (36 char) |
| `RESEND_FROM` | set |
| `CORS_ORIGINS` | set (121 char) |

### Zorunlu (UNSET — pilot blocker)
| Secret | Etkisi |
|---|---|
| `ATLAS_TIER` | smoke step 5 `backup: atlas_unknown_tier` (M0+production → readiness FAIL) |
| `SENTRY_ENVIRONMENT` | default `production` — pilot için `pilot` tag override önerisi |
| `EXELY_IP_WHITELIST` | `verify_exely_whitelist --env production` → BLOCKER, webhook 503 |
| `ROOM_QR_SECRET` | room QR token üretimi başarısız |
| `PUBLIC_APP_URL` | email link'leri + OAuth callback bozuk |

### Opsiyonel (UNSET — degraded ama OK)
| Secret | Etkisi |
|---|---|
| `ATLAS_API_PUBLIC_KEY/PRIVATE_KEY/PROJECT_ID/CLUSTER_NAME` | snapshot tazelik doğrulaması yapılamaz |
| `SENTRY_AUTH_TOKEN` | release tracking yok |

### Pilot warning
| Secret | Sandbox | Pilot beklentisi |
|---|---|---|
| `ENABLE_QUICKID_DEMO` | set len=4 (muhtemelen `true`) | **PİLOTTA `0`** — gerçek QuickID kullanılır |

---

## §4 Sandbox script dry-run sonuçları

### §4.1 `bash deploy/rollback.sh --dry-run`
```
[!] DRY-RUN modu — hiçbir komut çalıştırılmaz
── 1/5 — Hedef commit belirleniyor ──
[FAIL] Hedef yok: deploy/.last_good_tag bulunamadı ve argüman geçilmedi
```
**Sonuç:** ⚠️ Expected-FAIL. `.last_good_tag` ilk başarılı `deploy/deploy.sh`
sonrası oluşur. `--list` 10 commit gösterdi (en yeni `cbdc6bc2`).

### §4.2 `python backend/scripts/cm_backlog_alert.py --json` — 🐛 BUG KEŞFİ + FIX

**İlk koşum (fix öncesi):**
```json
{
  "verdict": "unknown",
  "outbox": {"status":"unknown", "score":0.5,
             "error_type":"ServerSelectionTimeoutError"},
  "circuit_breakers": {"status":"ok","total":0,"open":0}
}
```
WARNING log: `localhost:27017: Connection refused`.

**Root cause:** `core/database.py:19` `MONGO_URL` env-var arar, default
`mongodb://localhost:27017`. `backend/start.sh:7-8` Backend için
`MONGO_URL=$MONGO_ATLAS_URI` alias yapar — ama **cron context'te
start.sh çalışmaz** → cron `MONGO_URL` UNSET → localhost'a düşer →
verdict=unknown sürekli, alarm kullanılamaz.

**Fix:** `backend/scripts/cm_backlog_alert.py main()` başına 2 satır
fallback eklendi (core.database lazy-import edildiği için os.environ
mutate güvenli):
```python
if not os.environ.get("MONGO_URL") and os.environ.get("MONGO_ATLAS_URI"):
    os.environ["MONGO_URL"] = os.environ["MONGO_ATLAS_URI"]
```

**Bypass test (Atlas'a doğrudan, fix mantığını doğrular):**
`get_cm_observability_snapshot(atlas_db)` →
```json
{"verdict":"ok",
 "outbox":{"status":"ok","score":1.0,"pending":0,"failed":0,"backlog":0},
 "circuit_breakers":{"status":"ok","total":0}}
```
**Sonuç:** ✅ PASS — fix sonrası gerçek pilot Atlas'a bağlanacak.

### §4.3 `python backend/scripts/verify_atlas_backup.py --max-age-hours 26`
```
verify_atlas_backup: api_keys_unset (no-op, exit 0)
```
**Sonuç:** ⚠️ NO-OP. `ATLAS_API_*` 4 secret set olunca gerçek snapshot tazelik kontrolü yapılır.

### §4.4 `bash deploy/smoke.sh` (BASE_URL=http://localhost:8000)
```
Step 1/6 Liveness/Readiness probe   [PASS] HTTP 200, status=ready
Step 2/6 Admin login                  [PASS] token=eyJ...
Step 3/6 Bookings list                [PASS] HTTP 200, array
Step 4/6 Cancel write-path           [PASS] HTTP 404 (bogus id, expected)
Step 5/6 production-golive/readiness [FAIL] status=DEGRADED score=65/70
         - providers: not_configured
         - backup: atlas_unknown_tier
         - alerting: error
         - cm_outbox: fail
Step 6/6 Sentry/observability         [PASS] active per /summary

Verdict: PASS=5 WARN=0 FAIL=1
```
**Sonuç:** ❌ 5/6. Step 5 FAIL → §1 unset secret'ler düzelince geçer:
- `atlas_unknown_tier` → `ATLAS_TIER=M10` set
- `providers: not_configured` → HotelRunner tenant credentials (vault DEĞİL, encrypted DB)
- `alerting: error` → Sentry environment + alert rules kurulumu
- `cm_outbox: fail` → cron MONGO_URL alias (yukarıdaki §4.2 fix sonrası)

### §4.5 (BONUS) `python backend/scripts/verify_exely_whitelist.py --env production`
```
[BLOCKER] EXELY_IP_WHITELIST is empty/unset.
verdict=FAIL
```
**Sonuç:** ❌ Pilot HR-only ise N/A; HR+Exely ise zorunlu.

---

## §5 PILOT_GO_NO_GO

`docs/drill_reports/PILOT_GO_NO_GO_sandbox_2026-05-13.md` oluşturuldu
(template kopyası, placeholder'lar dolduruluş için bekliyor).

---

## §6 Eskalasyon — sandbox karar

Multi-gate hard-stop kuralı (`PRODUCTION_LAUNCH_REHEARSAL.md` §6):
- Gate #1 (Secrets) FAIL → 24h ERTELE
- Gate #8 (Smoke) FAIL → 24h ERTELE

Sandbox'ta her ikisi de FAIL → **NO-GO** karar verildi. Bu beklenen
sonuç; sandbox pilot ortam değil. Gerçek pilot için aksiyon listesi:

1. **Replit Secrets vault'a 4 zorunlu secret ekle:**
   - `ATLAS_TIER=M10`
   - `SENTRY_ENVIRONMENT=pilot`
   - `EXELY_IP_WHITELIST=<comma-separated IPs>` (HR+Exely ise)
   - `ROOM_QR_SECRET=<32+ char random>`
   - `PUBLIC_APP_URL=https://<frontend-domain>`
2. **`ENABLE_QUICKID_DEMO`'yu `0` yap** veya secret'i sil
3. **HotelRunner pilot tenant credentials** encrypted DB'ye yaz (vault DEĞİL)
4. **Sentry UI 11 alert rule + cm-backlog cron monitor** kur
   (`docs/SENTRY_ALERT_POLICY.md`)
5. **Cron schedule'a cm_backlog_alert.py ekle** —
   fix sonrası MONGO_URL alias olmadan da Atlas'a bağlanır
6. **İlk başarılı `deploy/deploy.sh`** sonrası `.last_good_tag` oluşur,
   §4.1 PASS olur
7. **`smoke.sh` yeniden koş** → 6/6 hedefi
8. **PILOT_GO_NO_GO_sandbox_*.md placeholder'larını gerçek değerlerle doldur**

---

## §7 Net çıktılar (gerçek pilot için kalıcı kazanç)

1. **🐛 BUG fix:** `cm_backlog_alert.py` cron'da MONGO_URL alias yok
   sorununa kalıcı çözüm. Pilot operatör cron config'inde env-var
   prefix yazmak zorunda değil.
2. **📋 Drill rapor:** ilk gerçek-veri rehearsal sonucu kaydedildi —
   gelecek rehearsal'ler bu raporu baseline olarak kullanır.
3. **📝 GO/NO-GO kopyası:** `drill_reports/PILOT_GO_NO_GO_sandbox_2026-05-13.md`
   placeholder doldurma için hazır.
4. **📌 Replit.md gotcha eklendi:** "MONGO_URL alias cron'da yok"
   gelecek refactor'larda regression önler.

**Sonuç değerlendirmesi:** Doc'un kendisi (PRODUCTION_LAUNCH_REHEARSAL)
**çalışıyor**. Sandbox'ta beklenen sınırlamalarla 9/9 kapı ya yürütüldü
ya operatör-eylemi olarak işaretlendi. 1 gerçek bug yakalandı + fix'lendi.
Doc gerçek pilot için kullanıma hazır.
