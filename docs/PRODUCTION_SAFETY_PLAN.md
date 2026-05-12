# Production Safety Plan — Pilot Öncesi Discovery + Yol Haritası

> **Amaç:** Yarın HotelRunner pilotu canlıya alındığında bir şey bozulursa
> sistem ya kendini korusun, ya açıkça uyarsın, ya da tek komutla geri
> dönülebilsin. Bu plan **yeni özellik değil**; canlı operasyon güvenliği
> içindir.
>
> **Yöntem:** 7 başlık altında: mevcut durum (kod referanslarıyla), risk,
> yapılacak iş, tahmini süre, pilot blocker mı, önerilen sıra.
>
> **Kapsam dışı:** Production deploy, secret rotation, gerçek smoke koşumu —
> bunları kullanıcı yapacak. Bu doküman sadece sandbox'ta yapılan kod
> keşfine dayanır.

---

## Yönetici özeti

| #   | Konu                                  | Mevcut Durum                  | Pilot Blocker? | Tahmini Süre |
| --- | ------------------------------------- | ----------------------------- | -------------- | ------------ |
| 1   | Tek komutlu rollback                  | ✅ **DONE** (12 May 2026)      | ~~EVET~~       | ~~2–3 saat~~ |
| 2   | Backup automation + durable storage   | ✅ **DONE** (Atlas-first, M10) | ~~EVET~~       | ~~4–6 saat~~ |
| 3   | Outbox / CM backlog görünürlük + alarm | Endpoint var, alarm yok       | **EVET**       | 3–4 saat     |
| 4   | Sentry alert policy                   | DSN var, routing yok          | **EVET**       | 1–2 saat     |
| 5   | Admin "Sistem Sağlığı" ekranı         | Sayfa var, parça eksik        | HAYIR          | 2–3 saat     |
| 6   | Kill-switch / feature flag standardı  | Altyapı var, env-var yok      | HAYIR          | 2 saat       |
| 7   | İlk 24 saat izleme runbook'u          | Go/No-Go içinde gömülü        | HAYIR          | 1 saat       |
| 8   | Replit OPS cheat-sheet                | YOK                           | HAYIR          | 1–2 saat     |

**Kalan pilot-blocker iş yükü:** #3 + #4 = ~4–6 saat.
**Tüm paket (kalan):** ~10–14 saat.

**Önerilen sıra:** ~~2 → 1~~ → **3 → 4** → 8 → 7 → 5 → 6.

---

## ✅ Kapsam #1 + #2 — Tamamlandı (12 Mayıs 2026)

**#2 (Backup) — Atlas-First yaklaşım:** Kullanıcı M10+ Atlas plan'ını
onayladı → `mongodump` + R2 upload **gereksiz** oldu. Atlas zaten
continuous backup + PITR sunuyor (S3 managed, retention configurable).

**Yazılan kod:**
- `backend/infra/atlas_backup_check.py` — URI-based Atlas detection +
  `resolve_backup_check()` Atlas-aware skor.
- `backend/scripts/verify_atlas_backup.py` — Atlas Admin API ile snapshot
  tazeliği doğrulama (opsiyonel, API key'siz no-op).
- `backend/infra/readiness_validator.py:97-112` — backup check Atlas-aware.
- `docs/ATLAS_BACKUP_AND_RESTORE.md` — restore senaryoları + tier
  matrisi + verification.

**#1 (Rollback) — Tek komutlu:**
- `deploy/rollback.sh` — `--list / --dry-run / [tag]` destekli, smoke
  otomatik koşar, başarıda `last_good_tag` günceller, başarısızlıkta
  `.rollback_from` sidecar bırakır.
- `deploy/deploy.sh` — başarılı deploy sonunda `IMAGE_TAG`'i
  `deploy/.last_good_tag`'e yazar, kullanıcıya `Rollback: bash
  deploy/rollback.sh` satırını gösterir.
- `docs/ROLLBACK.md` — 4 senaryo (kod hatası, auto-rollback, Atlas
  restore, tam felaket) + doğrulama komutları.

**Replit Secrets'a eklenmesi gereken (deploy zamanı):**
- `ATLAS_TIER=M10` (veya M20/M30)
- Opsiyonel: `ATLAS_API_PUBLIC_KEY`, `ATLAS_API_PRIVATE_KEY`,
  `ATLAS_PROJECT_ID`, `ATLAS_CLUSTER_NAME` — sadece snapshot tazelik
  doğrulaması için.

**Doğrulama (sandbox):**
- `bash -n deploy/{rollback,deploy,smoke}.sh` → tümü PASS
- `python3 -m py_compile backend/infra/atlas_backup_check.py
  backend/scripts/verify_atlas_backup.py
  backend/infra/readiness_validator.py` → tümü PASS
- Runtime: `resolve_backup_check()` M10 + Atlas SRV → `status="atlas_managed",
  score=1.0` (test edildi).

---

## Kapsam #1 — Tek komutlu rollback

### Mevcut durum
- ✅ `backend/ops/auto_rollback_engine.py:1-166` — metric-based rollback engine.
  `ROLLBACK_TRIGGERS` listesi (5xx rate, health endpoint down, DB connection
  fail, outbox backlog, import failure rate). `execute_rollback()` çağrıldığında
  `smoke_test_runner.run_all()` otomatik koşar (L153-154).
- ✅ `deploy/deploy.sh` — 179 satır, prod kurulum script'i (Docker compose,
  .env validation, certbot setup).
- ⚠️ `docs/PILOT_GO_NO_GO.md:502` — `bash deploy/deploy.sh --rollback` komutu
  REFERANS edilmiş AMA `deploy/deploy.sh` içinde `--rollback` parametresi
  GERÇEKTEN İŞLENMİYOR (script sadece deploy yolu içeriyor).
- ❌ `deploy/rollback.sh` — YOK.
- ❌ `docs/ROLLBACK.md` — YOK (DISASTER_RECOVERY.md ve INCIDENT_PLAYBOOK.md
  var ama "tek komutla geri dön" odaklı değil).

### Risk
Pilotta hata çıktığında kullanıcı kod bilmediği için "hangi compose tag'ine
döneceğim?" sorusunu yanıtlayamaz. `deploy.sh --rollback` referansı belge'de
olup script'te yoksa, **panik anında yanıltıcı**. Auto-rollback engine
metric-driven; manuel "şimdi geri al" düğmesi yok.

### Yapılacak iş
1. `deploy/rollback.sh` yaz: önceki imaj tag'ini bul, `docker compose down →
   docker compose up -d` previous tag ile, ardından `bash deploy/smoke.sh`
   otomatik koş, exit-code'a göre PASS/FAIL bildir.
2. `deploy/deploy.sh` her başarılı deploy sonrası mevcut imaj tag'ini
   `deploy/.last_good_tag` dosyasına yaz (rollback hedefi).
3. `docs/ROLLBACK.md` yaz: 1 sayfa, 4 senaryo (manuel, auto-rollback tetiklendi,
   DB restore, full DR), her birinde 5–8 satır kopyala-yapıştır komut.
4. `PILOT_GO_NO_GO_HR_TEMPLATE.md` §rollback satırını `deploy/rollback.sh`
   referansıyla güncelle.

### Süre
2–3 saat (kod 1–1.5 saat, doküman 1 saat, sandbox lint).

### Pilot blocker?
**EVET.** "Hata çıkarsa ne yapacağım?" sorusunun cevabı bugün net değil.

### Bağımlılık
Kapsam #2 (durable backup) öncelik: backup yoksa rollback bile veri kaybını
önlemez.

---

## Kapsam #2 — Backup automation + kalıcı (durable) yedek

### Mevcut durum
- ✅ `backend/infra/backup_manager.py:1-165` — `BackupManager` sınıfı,
  `mongodump` ile MongoDB backup. Default cron `0 2 * * *` (`BACKUP_CRON`,
  L7), retention `BACKUP_RETENTION_DAYS=30` (L75). 23 kritik koleksiyon
  hard-coded (L23-27).
- ✅ `backend/infra/readiness_validator.py:94-104` — backup readiness
  check (`enabled` ise score 1.0, değilse 0.3).
- ⚠️ `BACKUP_ENABLED` default **`false`** (L71). Production'da explicit
  set edilmediyse backup hiç koşmuyor.
- ⚠️ `BACKUP_PATH` default `/tmp/backups` (L73). Container restart'ta
  silinir — **yedeğin yedeği yok**.
- ❌ Durable upload (S3/R2/GCS) **kod olarak YOK.** `boto3`/`google.cloud`
  import'u backend'de yok. `docs/procedures/BACKUP_AND_RESTORE.md:127-138`
  bash script önerisi içeriyor ama implement edilmemiş.
- ❌ Celery beat'te backup task **kayıtlı değil**. `backend/celery_app.py:54-130`
  beat schedule'ında night_audit, archive, hrv2-shadow var; `backup_*` yok.
  Yani `BackupManager` sınıfı bir orchestrator tarafından çağrılmıyor —
  sadece API üzerinden manuel tetikleniyor olabilir (router incelenmeli).

### Risk
**EN KRİTİK GAP.** Pilotta veri bozulursa elde güvenilir geri dönüş noktası
**yok**. `BACKUP_ENABLED=true` set edilse bile `/tmp/backups` ephemeral.
Replit deployments restart'ta volume sıfırlanırsa yedek kaybolur.

### Yapılacak iş
1. **Backup'ı schedule'a bağla**: `backend/celery_app.py` beat'ine
   `backup-daily` task ekle (cron 02:00 UTC), `BackupManager.create_backup()`
   çağırır.
2. **Durable upload modülü yaz**: `backend/infra/backup_uploader.py` —
   tamamlanmış backup dizinini `tar.gz` yapıp S3/R2/GCS'e yükler. Env:
   `BACKUP_DURABLE_PROVIDER=s3|r2|gcs`, `BACKUP_DURABLE_BUCKET`,
   credentials Replit Secrets'tan. `boto3` (s3-compatible R2 dahil) ya
   da `google-cloud-storage` dependency ekle.
3. **`readiness_validator` backup check'ini sertleştir**: son başarılı
   backup 26 saatten eskiyse (24h + 2h tolerans) score 0.0, JSON'a
   `last_backup_age_hours` ekle. `PILOT_GO_NO_GO §4` bunu hard-blocker
   olarak işaretler.
4. **Restore drill'i durable storage'dan koş**: `tools/tenant_restore_drill.py`
   şu an local backup'tan restore ediyor; durable upload sonrası
   download-then-restore yolu eklenmeli.
5. `docs/procedures/BACKUP_AND_RESTORE.md` § "Durable Upload" bölümünü
   gerçek implementation'a göre yeniden yaz.

### Süre
4–6 saat (uploader 2–3 saat, beat task 30 dk, readiness check 1 saat,
drill yolu 1–1.5 saat).

### Pilot blocker?
**EVET — en kritik.** Bu yapılmadan satışa çıkmak veri kaybı kabul
etmek demektir.

### Önerilen provider
**Cloudflare R2** (S3-compatible API, çıkış ücretsiz, ~$0.015/GB depolama
— pilot için $1/ay altı). `boto3` ile aynı interface çalışır.

---

## Kapsam #3 — Outbox / CM backlog görünürlük + alarm

### Mevcut durum
- ✅ `backend/domains/channel_manager/monitoring/monitoring_router.py:67-106` —
  `GET /api/channel-manager/monitoring/overview` aggregate endpoint:
  system_health, providers, active_alerts, queue_depth, reconciliation
  open_cases, ingest/ari/recon/queue status, worker state.
- ✅ `aggregator.py:357-358` — outbox processed/failed/retry counter'ları
  in-memory (OutboxWorker `backend/core/outbox_worker.py:104-112`).
- ✅ `GET /api/channel-manager/unified-rate-manager/circuit-breakers` —
  Turu #4'te eklendi, breaker state listesi döner (`unified_rate_manager_router.py:1343`).
- ✅ `backend/ops/auto_rollback_engine.py:43-58` — `outbox_backlog` trigger
  threshold 500 events, action `alert_and_pause`.
- ⚠️ Outbox counter'ları **in-memory** (worker restart'ta sıfırlanır).
  Persisted backlog query'si var mı bilinmiyor (router'da
  `outbox_events.count_documents({status: "pending"})` görünmedi).
- ❌ `readiness_validator.py` outbox backlog'a ve circuit-breaker state'e
  **bakmıyor** (sadece backup, observability, alerting, env, exely).
- ❌ Alertmanager rule'ları (`infra/prometheus/alerts.yml`) outbox/CM
  spesifik kural içerip içermediği denetlenmedi.

### Risk
Pilotta HotelRunner 504 verirse outbox biriker; kullanıcı kontrol panelinde
"şu an kaç event pending?" cevabını tek bakışta göremezse rollback
kararı geç kalır. Worker restart'ında counter sıfırlandığı için "son 5
dakikada N hata" trendi kaybolur.

### Yapılacak iş
1. **Outbox persisted backlog query**: `outbox_events` koleksiyonunda
   `status ∈ {pending, retry, failed_permanent}` count'larını döndüren
   bir helper (varsa onaylanmalı; yoksa eklenmeli) ve
   `monitoring/overview` response'una `outbox_pending`/`outbox_failed`
   alanları eklenmeli.
2. **`readiness_validator`'a outbox + breaker check'i ekle**:
   - `outbox_pending > 500` → score 0.0, status `degraded`
   - herhangi bir circuit breaker `OPEN` → score 0.0, status `degraded`
3. **Prometheus alert rule'ları** (`infra/prometheus/alerts.yml`):
   - `OutboxBacklogHigh` (pending > 100, 5 dk, warning)
   - `OutboxBacklogCritical` (pending > 500, 5 dk, critical)
   - `CircuitBreakerOpen` (any breaker OPEN > 5 dk, critical)
   - `HRSyncErrorRateHigh` (HR push errors > %10, 10 dk, critical)
4. **Alertmanager routing** (`infra/alertmanager/alertmanager.yml`) →
   #4 ile birleştir.

### Süre
3–4 saat (helper + readiness 1–1.5 saat, alert rules + routing 1.5–2 saat,
test 30 dk).

### Pilot blocker?
**EVET.** Görünürlük olmadan rollback tetikleyici doğru zamanda algılanamaz.

---

## Kapsam #4 — Sentry / hata alarmı netleştirme

### Mevcut durum
- ✅ `backend/infra/cloud_observability.py:90-130` — Sentry SDK init,
  DSN registration, environment tagging.
- ✅ Frontend `VITE_SENTRY_DSN` Replit Secrets'ta mevcut.
- ✅ `infra/alertmanager/alertmanager.yml` ve `infra/prometheus/alerts.yml`
  dosyaları mevcut (içerik denetlenmedi).
- ❌ Sentry için **alert routing/threshold konfigürasyonu YOK**. Hangi
  hata kime gider, hangi tag rollback tetikler — belge yok.
- ❌ Sentry environment ayrımı (`production` vs `pilot` vs `staging`)
  doğrulanmadı.

### Risk
Pilotta yeni ERROR çıkar ama kimse fark etmez. `tenant_leak` gibi kritik
tag varsa anında müdahale gerekir; manuel email/Slack rotası tanımlı değil.

### Yapılacak iş
1. **`docs/SENTRY_ALERT_POLICY.md`** yaz, 1 sayfa:
   - Environment matrix: development / staging / pilot / production
   - Alert seviye tablosu:
     | Tag/Pattern | Severity | Aksiyon | Bildirim |
     |---|---|---|---|
     | `tenant_leak:*` | CRITICAL | Otomatik rollback + manuel doğrulama | Email + WhatsApp |
     | `hr_sync_error` rate > %10 | CRITICAL | CM manuel mod | Email |
     | 5xx rate > %5 (5 dk) | CRITICAL | Auto-rollback engine | Email |
     | `auth_failure_spike` | WARNING | İzle | Email |
     | Yeni unique error | INFO | Günlük rapor | Email digest |
2. **Sentry dashboard'da alert rule'ları el ile yapılandır** (kullanıcı yapacak;
   bu doküman talimat sağlar).
3. **`backend/infra/cloud_observability.py`** — `before_send` hook'unda
   `tenant_leak` tag'i set eden bir filter (varsa onaylanmalı; yoksa
   eklenmeli).
4. Replit Secrets'ta `SENTRY_ENVIRONMENT=pilot` set et (deploy adımı).

### Süre
1–2 saat (doküman 1 saat, hook check 30 dk, tag setup 30 dk).

### Pilot blocker?
**EVET.** Alarm yoksa pilot izlemesi gözle yapılır — sürdürülebilir değil.

---

## Kapsam #5 — Admin "Sistem Sağlığı" ekranı

### Mevcut durum
- ✅ `frontend/src/pages/SystemHealthDashboard.jsx` — sayfa mevcut, route
  `/system-health` (`infrastructure.js:12`, `wrapLayout: true`,
  `layoutModule: "system_health"`).
- ✅ Admin tab'ları: `ReadinessTab.jsx`, `SyncHealthTab.jsx`,
  `ObservabilityTab.jsx`, `HealthTrendTab.jsx`, `ConnectorHealthTab.jsx`.
- ✅ `HRv2OpsDashboard.jsx`, `ChannelOpsPage.jsx` HR'a özel paneller.
- ⚠️ Bu ekranların pilot operatörü için "tek bakışta yeşil/sarı/kırmızı"
  özet kartı sağlayıp sağlamadığı doğrulanmadı (sayfaları okumadık).
- ❌ "Son backup zamanı", "outbox backlog", "circuit breaker durumu",
  "son smoke sonucu" tek bir kart üzerinde toplanmamış olabilir.

### Risk
Mevcut ekranlar geliştirici odaklı. Pilot operatörü (kod bilmeyen)
"şu an her şey yolunda mı?" sorusuna 1 saniyede cevap alamayabilir.

### Yapılacak iş
1. `SystemHealthDashboard.jsx` üstüne **Operasyon Durum Kartı** ekle:
   - 6 küçük pill: API ✅ / DB ✅ / Redis ✅ / Backup ✅ (son: 4h önce) /
     HR Bağlantı ✅ / Circuit Breaker ✅
   - Tek bir kırmızı varsa büyük uyarı banner'ı + "Cheat-sheet'e git" CTA.
2. Backend tarafında `GET /api/ops/system-summary` aggregate endpoint
   (zaten var olan parçaları birleştirir: readiness + monitoring/overview
   + circuit-breakers + son backup zamanı). Yeni mantık YOK, sadece
   facade.
3. Dil: Türkçe, sade. "Outbox backlog: 12 event" değil "Bekleyen
   bildirim: 12 (normal)".

### Süre
2–3 saat (backend facade 1 saat, frontend kart 1–2 saat).

### Pilot blocker?
**HAYIR.** Mevcut tab'lar yeterli; bu kart "rahatlık" maddesidir. #3 ve
#4 alarmlar varsa sayfayı sürekli açık tutmaya gerek kalmaz.

---

## Kapsam #6 — Kill-switch / özellik kapatma anahtarları

### Mevcut durum
- ✅ `backend/core/feature_flags.py:1-80` — `feature_flags` MongoDB
  koleksiyonu, `kill_switch=True` per-flag, tenant override, percentage
  rollout, expiry. **Altyapı sağlam.**
- ✅ `is_flag_enabled(flag_key, tenant_id)` API public.
- ⚠️ Mevcut env-var kill-switch'ler **dağınık**:
  - `BACKUP_ENABLED` (`backup_manager.py:71`)
  - `ENABLE_QUICKID_DEMO` (`quick_id_proxy.py`)
  - `ENABLE_SETUP_ENDPOINTS` (`auth.py`)
  - `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK`, `ALLOW_UNSIGNED_*`
    (`server.py:586` bypass flags)
- ❌ Kullanıcının istediği `ENABLE_HOTELRUNNER_PUSH`,
  `ENABLE_EXELY_WEBHOOK`, `ENABLE_CM_OUTBOX_DISPATCH`, `ENABLE_AI_FEATURES`,
  `ENABLE_BULK_RESOLVE`, `ENABLE_PAYMENT_ACTIONS` **yok**.

### Risk
Pilotta bir modül bozulursa kullanıcı tüm uygulamayı kapatmak yerine
sadece o modülü durdurmak ister; bugün bunu yapacak runtime switch
yok (kod değişikliği + redeploy gerekir).

### Yapılacak iş
1. **`docs/KILL_SWITCHES.md`** yaz: hangi flag mevcut (env vs DB),
   hangisi eklenmeli, nasıl set edilir.
2. **6 yeni feature flag** seed et (`feature_flags` koleksiyonuna):
   `hotelrunner_push`, `exely_webhook`, `cm_outbox_dispatch`,
   `ai_features`, `bulk_resolve`, `payment_actions`. Hepsi default
   `enabled=true, kill_switch=false`.
3. **Hot-path entegrasyonu** (en kritik 2 tanesi):
   - `outbox_dispatcher.py` döngüsünün başında
     `if not await is_flag_enabled("cm_outbox_dispatch"): return`.
   - HR push noktasında (`providers/hotelrunner_sync.py` veya benzeri)
     `if not await is_flag_enabled("hotelrunner_push"): return ProviderResult(success=False, error_type="KillSwitch")`.
4. **Admin UI** (varsa `feature_flags` yönetim ekranı): bir butonla
   `kill_switch=true` toggle.

### Süre
2 saat (seed + 2 hot-path entegrasyonu + doküman).

### Pilot blocker?
**HAYIR.** Mevcut env-var bypass flag'leri ve circuit-breaker'lar sınırlı
ama yeterli koruma sağlar. Bu paket "lüks", pilot sonrası ilk hafta
yapılabilir.

---

## Kapsam #7 — İlk 24 saat izleme runbook'u

### Mevcut durum
- ✅ `docs/PILOT_GO_NO_GO.md:485-513` — "Rollback trigger checklist (ilk
  24 saat post-go-live)" bölümü, threshold'larla.
- ✅ `docs/procedures/GO_LIVE_RUNBOOK.md` (226 satır) — go-live prosedürü.
- ✅ `docs/procedures/INCIDENT_PLAYBOOK.md` (291 satır) — olay yönetimi.
- ⚠️ "Saat saat ne yapacağım" formatı **yok**. Eşikler dağınık 3 dosyada.
- ⚠️ Operatör (pilot lead) için tek sayfa zaman çizelgesi eksik.

### Risk
Pilot lead ilk 24 saat boyunca farklı dokümanlar arasında gezinmek
zorunda kalır; izleme sıklığı net değil.

### Yapılacak iş
1. `docs/PILOT_FIRST_24H_MONITORING.md` yaz, ~1 sayfa:
   - **0-1 saat**: her 10 dk smoke + sentry ERROR sayısı + login success rate
   - **1-6 saat**: her 30 dk CM monitoring/overview + outbox pending count
   - **6-24 saat**: her 2 saatte readiness + backup status + breaker state
   - **Karar matrisi**: hangi metrik hangi eşikte → manuel/auto/rollback
2. Eşikleri `auto_rollback_engine.py:ROLLBACK_TRIGGERS` ve
   `PILOT_GO_NO_GO §rollback` ile **birebir senkron** tut.

### Süre
1 saat (mevcut içeriklerden derleme).

### Pilot blocker?
**HAYIR.** Var olan içerikler yeterli; bu derleme rahatlık katar.

---

## Kapsam #8 — Replit OPS cheat-sheet

### Mevcut durum
- ❌ `docs/OPS_CHEATSHEET_REPLIT.md` **YOK**.
- ✅ Komutlar dağınık şekilde mevcut: `deploy/SMOKE.md`,
  `deploy/DEPLOYMENT_GUIDE.md`, `docs/PRE_DEPLOY_CHECKLIST.md`,
  `docs/PILOT_GO_NO_GO_HR_TEMPLATE.md`.

### Risk
Pilot anında kullanıcı (Murat) komutları arar; tek sayfa kopyala-yapıştır
referansı yoksa zaman kaybı + hata olasılığı.

### Yapılacak iş
1. `docs/OPS_CHEATSHEET_REPLIT.md` yaz, 1 sayfa, sadece komutlar:
   ```
   ## Sağlık kontrolü
   curl -s https://<API>/api/health | jq

   ## Smoke (6 adım)
   bash deploy/smoke.sh

   ## Backup tetikle (manuel)
   <komut>

   ## Son backup zamanı
   curl -s https://<API>/api/admin/backup-status | jq .last_successful

   ## Outbox pending sayısı
   curl -s https://<API>/api/channel-manager/monitoring/overview | jq .outbox_pending

   ## Circuit breaker durumu
   curl -s https://<API>/api/channel-manager/unified-rate-manager/circuit-breakers | jq

   ## Kill switch (HR push'u kapat)
   <admin UI veya curl>

   ## Rollback (tek komut)
   bash deploy/rollback.sh

   ## Sentry son 1 saat ERROR
   <Sentry URL>
   ```
2. Markdown'da her bölüm ayrı `<details>` veya emoji-sız başlıkla.
3. Hiçbir açıklama metni yok — sadece komut + 1 satır ne işe yaradığı.

### Süre
1–2 saat (#1, #2, #3, #6 implement edildikten sonra yazılır — komutlar
gerçek olmalı).

### Pilot blocker?
**HAYIR** (içerikse) ama **EVET** (kullanıcı pratikliği için pilot anında
elin altında olması şart). #1-#6 tamamlandıktan sonra son adım olarak
yazılır.

---

## Önerilen implementation sırası ve gerekçesi

| Sıra | Paket            | Neden bu sıra?                                                                  |
| ---- | ---------------- | ------------------------------------------------------------------------------- |
| 1    | #2 Backup durable | En kritik gap. Diğer her şey bu olmadan anlamsız.                              |
| 2    | #1 Rollback      | Backup hazırsa rollback güvenli. Dokümanda referans verilen `--rollback` yok.   |
| 3    | #3 CM görünürlük | Rollback tetikleyicilerinin görünmesi şart. Auto-rollback engine bağımlısı.    |
| 4    | #4 Sentry policy | #3 ile birlikte alert routing'i tamamlar.                                       |
| 5    | #8 Cheat-sheet   | #1-#4 komutları gerçek olmalı; en sona yazılır ama kullanıcı için ilk açılır.  |
| 6    | #7 24h runbook   | Mevcut içerikten derleme; #3+#4 eşikleri ile senkron olmalı.                   |
| 7    | #5 Admin kart    | Pilot lead rahatlığı; #3 facade'ı kullanır.                                    |
| 8    | #6 Kill-switch   | Lüks. Mevcut bypass flag'leri yeterli ilk pilot için.                          |

**Pilot-blocker kesim çizgisi:** sıra 1-4 (#2, #1, #3, #4) — bunlar
yapılmadan canlıya çıkma. Sıra 5-8 pilot sonrası ilk hafta.

---

## Pilot-blocker özet tablosu

```
[ ] #2 Backup automation + durable storage (S3/R2 upload)
[ ] #1 deploy/rollback.sh + ROLLBACK.md
[ ] #3 Outbox/CM aggregate + readiness check + alert rules
[ ] #4 SENTRY_ALERT_POLICY.md + Sentry dashboard rule'ları
```

Bu 4 maddesi tamamlandığında Murat "kod bilmiyorum, canlıda ne yapacağım?"
sorusuna cevap olarak şunu der:

> "Sentry alarm verirse e-posta'ya bakarım. Cheat-sheet'ten outbox/breaker
> durumunu kontrol ederim. Kötüyse `bash deploy/rollback.sh` çalıştırırım,
> son backup'tan restore yolu hazır."

---

## Bilinmeyenler (bu plan dışı, ek discovery gerekirse)

1. `outbox_events` koleksiyonunda persisted backlog query'sinin
   `monitoring/overview` response'una eklenmiş olup olmadığı —
   `aggregator.py:357-358` in-memory counter dedi, persisted query var
   mı netleşmedi.
2. Frontend `feature_flags` yönetim ekranı var mı — kullanıcının kill
   switch'i tek tıkla toggle edebileceği UI mevcut mu, yoksa sadece
   API mi? Discovery genişletilebilir.
3. `infra/prometheus/alerts.yml` ve `infra/alertmanager/alertmanager.yml`
   içeriği denetlenmedi — bazı kuralların zaten mevcut olabileceğini
   doğrulamak #3'ü %30 azaltabilir.

---

**Hazırlayan:** Replit Agent (sandbox discovery)
**Tarih:** 12 Mayıs 2026
**Dayanak:** sandbox'ta kod referansı bazlı keşif; production deploy
durumu doğrulanmadı.
