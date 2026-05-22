# Syroce PMS — Gotchas

Bu dosya `replit.md`'den çıkarılan ayrıntılı gotcha kayıtlarını içerir. `replit.md` artık her alt-başlığın bir cümlelik özetini + bu dosyaya bağlantı tutar; ayrıntı, dosya/satır referansları ve tarihçe burada.

---

## Testing

### UI Business E2E Suite (May 2026)

`frontend/playwright.business.config.js` + `frontend/e2e-business/` (smoke ile birlikte yaşar, ayrı klasör). Komut: `cd frontend && yarn test:e2e:business` (`:list` ile dry-enumerate). Env zorunlu: `E2E_BASE_URL`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD` (config fail-fast). Pilot/staging'e koşar; **dış servisler (gerçek payment / OTA push / SMS / e-posta / KVKK)** spec içinde `SKIP/REVIEW` olarak işaretli — asla canlıya etmez.

20 spec dosyası (01-20), kapsam-bazlı: auth-nav / dashboard-health / reservation / checkin-checkout / folio / invoice / mice / housekeeping / guest-crm / users-roles / channel-manager / rate-inventory / payments / reports / notifications / settings / audit-log / security-rbac / responsive / recap. Adım sayacı: PASS/FAIL/REVIEW/SKIP — `fixtures/recorder.js:rec(testInfo, {module, scope, step, status, endpoint, http, note})` annotation ile kayıt.

**Auth flow**: `global-setup.js` bir kez UI login yapar → `e2e-business/.auth/admin.json` storageState; `/api/auth/login` ile bearer token cache → `e2e-business/.auth/token.json` (api fixture okur).

**Test data**: `factory.*` `E2E_<ts36>_KIND` prefix; `trackEntity({kind, id, label, cleanup})` registry → reporter'da inventory tablosu. **Soft-fail**: feature/page yoksa REVIEW (FAIL değil) — pilot dataset boş olabilir.

**Custom reporter** `markdown-reporter.mjs` → `docs/drill_reports/YYYYMMDD_full_ui_business_e2e.md` (yönetici özeti / modül tablosu / kritik FAIL / test verisi / REVIEW+SKIP / risk P0-P3 / `GO|GO-WITH-WATCH|NO-GO`). HTML: `frontend/playwright-business-report/`; trace+video+screenshot: `frontend/test-results-business/`.

**Helper gotcha**: spec'lerden import edilen helper'lar Playwright transform ile CJS'e dönüştüğü için `import.meta.url` kullanılmaz — yerine `process.cwd()` (Playwright koşumunda `frontend/` döner) kullanıldı (`fixtures/data-factory.js`, `fixtures/api.js`, `global-setup.js`). Reporter `.mjs` çünkü Playwright reporter'ı `require()` ile yükler ve package.json'da `"type": "module"` yok.

### UI E2E Smoke Suite (May 2026)

`frontend/playwright.smoke.config.js` + `frontend/e2e-smoke/` (mevcut `frontend/e2e/` happy-path suite'inden ayrı, çakışmaz). Komut: `cd frontend && yarn test:e2e:smoke`. Env zorunlu: `E2E_BASE_URL`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD` (hardcoded fallback YOK — `fixtures.js:requireEnv` eksikse fail-fast). 24 route × 2 project (`desktop` 1440×900 + `mobile` Pixel 7) = 48 test.

**Critical** (17 route, fail = suite FAIL): Dashboard, Sistem Sağlığı, Channels Hub/CM Dashboard/Unified Rate Manager/Channel Connections/Ops/Conflict Queue (`/channels?tab=conflicts`), Rezervasyon Takvimi/PMS/PMS Operasyonlar, Folio/Grup Folio, Admin Control Panel/Kullanıcı-Rol (`/admin/user-roles`), Ayarlar, Güvenlik. **Secondary** (7 route, soft warning): Control Plane, Audit Timeline, Rate Manager, İK, Tedarik Pazarı, Satınalma.

Her route için: navigate → boş ekran/404/500/Error UI tespit (`inspectPageContent`) + console error + network 4xx/5xx (allowlist'li: i18next/Sentry beacon/health probe 503 vb.) + güvenli buton tıklama (yalnız `Yenile`/`Refresh`/`Ara`/`Search` regex; destructive blacklist: sil/iptal/refund/void/vardiya kapat/çıkış).

**Çıktı**: HTML report `frontend/playwright-smoke-report/` + custom Markdown reporter `docs/drill_reports/YYYYMMDD_ui_e2e_smoke.md` (özet + failed steps + tüm route matrisı + safe-click özeti + artifact path'leri) + trace/video/screenshot `frontend/test-results-smoke/`. Catalog: `frontend/e2e-smoke/routes.js` (`ROUTES` + `CONSOLE_ERROR_ALLOWLIST` + `NETWORK_ERROR_ALLOWLIST`).

### F8A Stress Suite — Front Office + Folio + Housekeeping (May 2026)

`frontend/playwright.stress.config.js` + `frontend/e2e-stress/` (smoke/business ile çakışmaz, ayrı project=`stress`). 4 spec (`02-day-turnover`, `03-room-move`, `04-folio-mass`, `08-housekeeping-mass`) × Setup+A..F = 26 test toplamda. F7 fixture/helper'larını reuse eder: `fixtures/stress-helpers.js`, `global-setup.js` (500-oda seed + 5-gate kontrolü), `global-teardown.js` (cleanup#1 + idempotent cleanup#2 + pilot drift diff). Custom `markdown-reporter.mjs` → `docs/drill_reports/YYYYMMDD_stress_<TAG>.md` (`STRESS_REPORT_TAG` env).

**Defans invariant'ları (her run'da doğrulanır)**: (a) `gates`: 5/5 true (`env_stress_tid_present`, `target_matches_stress_tid`, `pilot_tid_not_targeted`, `destructive_stress_allowed`, `external_dry_run`), (b) `external_calls_made: []` (OTA/SMS/email/payment GW dispatch=0; `E2E_EXTERNAL_DRY_RUN=true` zorunlu), (c) `cleanup#1.deleted_total ≈ 5500` + `cleanup#2.idempotent=true`, (d) `pilot_diff.drift=0` (PILOT_TENANT_ID baseline=after).

**Backend workflow override (opt-in per stress run)**: Default `Backend API` workflow `bash backend/start.sh` (safe, fail-closed; `E2E_ALLOW_DESTRUCTIVE_STRESS` ve stress tenant ID'leri ENV'de YOK). Stres koşumu için operatör explicit opt-in yapar — workflow command'ını geçici olarak `E2E_ALLOW_DESTRUCTIVE_STRESS=true E2E_EXTERNAL_DRY_RUN=true E2E_STRESS_TENANT_ID=<stress-tid> PILOT_TENANT_ID=<pilot-tid> bash backend/start.sh` ile değiştirir, koşum bittikten sonra default'a döndürür. Always-on env injection güvenlik regresyonudur (architect feedback May 2026); production safety pack'in fail-closed prensibi gereği destructive flag'lar default'ta KAPALI olmalı.

**Replit sandbox 110s tool budget gotcha**: agent bash tool çağrı süresi ~110s ile sınırlı; setsid/nohup detached playwright süreçleri tool çağrısı bittikten ~3-5dk sonra reaper tarafından öldürülüyor. Çözüm: chunked sync runs (`--workers=4 -g <pattern>` ile Setup+drift / A+B / C / D+E gibi ≤8-15 test'lik gruplar; her grup ≤90s). Her chunk kendi `STRESS_REPORT_TAG` ile bağımsız raporlanır; canonical aggregate report (`f8a_frontoffice_folio_hk`) chunk'ları cross-reference eder. F8A ilk koşum: 26/26 test PASS (FAIL=0), defans katmanı 5/5 chunk yeşil; aggregate finding **P1=1 (folio-mass A/B/C batch s400) + P2=1 (room-move pozitif yol target dolu)** → ⚠️ **GO WITH WATCH** (`docs/drill_reports/20260514_stress_f8a_frontoffice_folio_hk.md` §10 chunk tablosu + §11 finding detayı + §12 verdict).

**Full one-shot koşum (CI, May 2026 — task #163)**: Replit sandbox'ın chunked workaround'una karşılık `.github/workflows/stress.yml` GitHub Actions job'u tüm 26 testi tek Playwright süreciyle (workers=1, no `-g` filter, deterministic seed→tests→cleanup) gece 02:30 UTC cron'unda + manuel `workflow_dispatch` ile koşturur. Tek konsolide drill report (`STRESS_REPORT_TAG=f8a_frontoffice_folio_hk`) üretir; chunked-run'ın yakalayamayacağı ordering / state-sharing regresyonlarını yakalar. Hard-fail kapıları: (1) pre-flight secret + `STRESS_TENANT_ID != PILOT_TENANT_ID` checki, (2) Playwright exit code (globalSetup 5-gate + `external_calls_made:[]` throw'ları + globalTeardown cleanup/idempotent/pilot drift throw'ları + spec içi `expect().not.toBe('FAIL')`), (3) post-step verdict scrape — drill report `Final verdict` satırı `NO-GO` ise job fail. Job artifact'leri: HTML report (30 gün), drill report MD (90 gün), trace/video (14 gün). Job için gereken GH secrets: `STRESS_E2E_BASE_URL`, `STRESS_PILOT_ADMIN_EMAIL/PASSWORD`, `STRESS_TENANT_ADMIN_EMAIL/PASSWORD`, `STRESS_TENANT_ID`, `PILOT_TENANT_ID`. **Slack bildirim akışı (task #164)**: Job fail (Playwright exit≠0, pre-flight/install fail, veya verdict_check'in NO-GO abort'u) durumunda `Notify Slack on failure / NO-GO` step'i `STRESS_SLACK_WEBHOOK_URL` secret'ine `:rotating_light:` mesaj POST eder; mesaj fail step adı (steps.<id>.outcome taraması) + verdict satırı + run URL + drill report path içerir. Verdict GO WITH WATCH ise düşük öncelikli `:warning:` mesaj atılır (job geçer). Webhook secret set değilse step skip olur (notify yokluğu job'ı battırmaz); `continue-on-error: true` ile Slack outage da test verdict'ini değiştirmez. GitHub Actions varsayılan e-postası cron run'da author=last pusher olduğu için anlamsız — Slack zorunlu kanal.

**Stress credentials**: `E2E_STRESS_ADMIN_EMAIL` / `E2E_STRESS_ADMIN_PASSWORD` (`playwright.stress.config.js` requires bunları, `.local/stress_tenant_credentials.txt` gitignored dosyada). Password'da `&@` gibi shell-meta karakter olabilir → `source` ile yüklenmez; python `open().read()` parse + `subprocess.run(env=...)` zorunlu (bkz. `/tmp/run_f8a.py` pattern). Pilot creds (`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`) replit secrets'ten gelir; setup hem stress hem pilot login'i (super_admin) yapar.

**Defense invariants — runtime-enforced (May 2026 hardening)**: `global-setup.js` seedResp'den 5 backend gate'i de hard-assert eder (failed → throw); `global-teardown.js` cleanup#1 fail / cleanup#2 non-idempotent / pilot drift!=0 durumlarında throw atar (process exit non-zero). Helper-level `fetchAllByPrefix` artık `stress_seed===true` fallback'ini KULLANMAZ — yalnız aktif round prefix'i geçen item'lar döner (cross-round leak defansı, `stress-helpers.js:22-30`).

---

## Conventions (always-on rules)

- **API Call Conventions**: Use relative paths WITHOUT `/api/` for `axios` calls; use `/api/` explicitly for native `fetch`.
- **Color Palette Convention**: Migrate from `purple-*` to `indigo-*` and `orange-*` to `amber-*` for Tailwind classes. Do not use `purple` or `orange` for new code.
- **In-App Dialog System**: Use `frontend/src/lib/dialogs.js` Promise API (`confirmDialog/alertDialog/promptDialog`) instead of native `window.alert/confirm/prompt`.
- **Walk-in Placeholder Guest Names**: API responses replace placeholder names (e.g., "C4", "X") with `Walk-in Misafir #XXXX` while preserving original DB values.
- **Image Uploads**: Strict validation for type, size, and dimensions.
- **Outbound HTTP Calls**: Tenant-configurable outbound URLs are protected with DNS-rebinding-safe transport, IP allowlisting, and transport pinning.

---

## Auth, security & infra

- **JWT Lifespan**: Backend default `JWT_EXPIRATION_MINUTES=15` overridden to `10080` (7 days) in Replit Secrets. Frontend attempts silent refresh on 401. Revocation is active.
- **Production Secret Management**: Critical secrets like `JWT_SECRET` must be set via Replit Secrets vault in production; hardcoded values may block startup.
- **Auth Cache Invalidation**: Handled via Redis pub/sub in multi-worker environments.
- **WS Redis Pub/Sub Circuit Breaker**: Prevents log/CPU spam by enforcing a cool-down period if the Redis listener fast-exits repeatedly.
- **CORS Configuration**: Ensure `CORS_ORIGINS` is correctly set in `.replit`.
- **MongoDB Atlas 500-Collection Limit**: Workarounds like embedded arrays or discriminator fields are used.
- **Night Audit N+1 Issues**: Optimized with `asyncio.gather` and bulk operations; avoid sequential DB calls in loops.
- **HotelRunner Pull Retries**: `sync_scheduler.pull_for_tenant` initializes `HotelRunnerProvider(max_retries=…)` per call. Manual sync uses 3, scheduled cycles use 2 (was 0 — caused unhandled transient 504s to surface as ERROR logs even though the next cycle would compensate). With `base_delay=2.0`, `jitter=0.5`, 2 retries add ~3–9s (avg ~6s) — well within the 3-min cycle. Keep ≥1 to absorb single-shot HotelRunner gateway 504/timeouts.
- **CapX Integration**: Integration with A-plan via encrypted tenant credentials and event-driven updates.
- **Exely Webhook**: Requires `EXELY_IP_WHITELIST` (literal comma-separated IPv4/IPv6, NOT CIDR — webhook does literal string match at `exely_webhook_router.py:394`); CIDR is only valid for `EXELY_TRUSTED_PROXY_IPS`. Pre-deploy verification: `python backend/scripts/verify_exely_whitelist.py --env production --expect-ips "$PILOT_EXELY_IPS"` (PASS/REVIEW/FAIL verdict, IPs redacted `1.2.3.4 → 1.2.x.4`); same `verify()` wired into `infra/readiness_validator.py` (alt-check `exely_whitelist`, counts only) and `server.py` startup guardrail (CRITICAL log, no abort). 46 tests in `tests/test_verify_exely_whitelist.py` + `tests/test_readiness_validator_exely_check.py`.

---

## Design system & layout

### Sprint A Design System (May 2026)

Use `<PageHeader icon title subtitle actions>` (`frontend/src/components/ui/page-header.jsx`) for page tops; `<KpiCard icon label value sub intent highlight active onClick>` (`frontend/src/components/ui/kpi-card.jsx`) for KPI grids — `intent` palette: `info` (sky), `success` (emerald), `warning` (amber), `danger` (rose), `neutral` (slate), `default`. Interactive KpiCard auto-adds `role=button + tabIndex=0 + Enter/Space + focus-visible`. Use `<StatusBadge intent icon>` (`frontend/src/components/ui/status-badge.jsx`) for status pills (same palette).

Standards: Yenile button always `<Button variant="outline" size="sm"><RefreshCw className="w-4 h-4 mr-1.5"/>Yenile</Button>`; primary CTA = default Button (siyah dolu) — gradient/blue/green özel renk YOK; emoji yok.

**İSTİSNA**: ReservationCalendar "Rezervasyon ekle" butonu **bilinçli** amber kaldı (en sık kullanılan marka aksiyonu). Para birimi: `formatCurrency(amount, currency || 'TRY')` from `frontend/src/lib/currency.js`. Tarih lokali: takvim gün kısaltmaları `Pzt/Çar`, date range `month: 'long'` (Mayıs).

12 pilot pages migrated (DepartureList/NoShowToday/WakeUpCalls/LostFound/DepositTracking/ArrivalList/Housekeeping/Maintenance/NightAudit/FrontdeskAudit/RMSModule/Mailing); Yenile butonu `?refresh=1` ile cache_manager `_nocache` kwarg'ını tetikler.

### Pages Layout Wrap (Current Default — M5, May 2026)

Routes own the Layout sarımı, NOT pages. Add `wrapLayout: true, layoutModule: "..."` to the route entry in `frontend/src/routes/routeDefinitions.jsx`; the page returns just its content (no `import Layout`, no `<Layout>` JSX).

**Önemli**: `layoutModule` değeri NAV_ITEMS'daki gerçek `key` ile eşleşmeli — boş veya yanlış key ("dashboard" gibi placeholder) bırakılırsa standalone "Kontrol Paneli" butonu sürekli aktif görünür ve üst menüde aynı anda iki sekme mavi çıkar.

118/123 pages migrated via `tools/codemod-layout/codemod.mjs`; 11 intentionally retain in-page `<Layout>` (6 use `MaybeLayout` for hub embed, 4 imported but never routed, 1 `ReservationCalendar.jsx` returns two distinct `currentModule` values conditionally).

**Regression guard**: `cd frontend && yarn guard:layout` (or `node tools/codemod-layout/guard.mjs`) fails if any route with `wrapLayout: true` points to a page that still imports `Layout` — prevents double-wrap.

---

## CM-Hardening Series (May 2026 — DONE)

Full architecture, test pins, file/line references → `docs/adr/2026-05-cm-hardening.md`.

- **Turu #1a/#1b/#1c/#2**: Overbooking alert emission + Conflict Queue API + UI + Bulk Resolve. HotelRunner provider'da transactional booking metodu YOK (cancel bile inventory recompute kullanır).
- **Turu #3a/#3b**: No-Show OTA Outbox Parity (event production + HotelRunner inventory recompute, Strategy A). `outbox_dispatcher.EVENT_TYPE_TO_CM_EVENT["booking.no_show.v1"] = "booking_no_show"`.
- **Turu #3c (DEFERRED, Discovery Complete)**: Exely no-show parity gap — repo'da iki paralel CM modülü ve farklı `ConnectorProvider` enum'ları (`channel_manager/domain/models/connector_account.py:18` HOTELRUNNER/SITEMINDER/CHANNEX vs `domains/channel_manager/data_model.py:29` HOTELRUNNER/EXELY). Exely conn'lar ayrı `exely_connections` koleksiyonunda → `EventSyncService` boş liste döner → outbox sessizce yutar. Pilot'ta Exely müşterisi yok, periyodik `exely_pull_worker.py` (180s) gap'i kapsıyor. Strategy A (~4-6h, ÖNERİLEN) vs Strategy B (~1-2g, full unification) — ADR'de tam akış haritası.
- **Turu #4 (Stop-Sale Circuit Breaker)**: `provider_failover.CircuitBreaker` HR `push_daily_inventory`+`push_date_range_inventory` ve Exely `push_ari` etrafında sarıldı. Per-connection key (`hotelrunner:{conn_id}` / `exely:{conn_id}`). Defaults: `failure_threshold=5`, `recovery_timeout=60s`, `half_open_max_calls=3`. Breaker OPEN iken `ProviderResult(success=False, error_type="CircuitOpen", metadata.circuit_open=True)`. UI: `GET /api/channel-manager/unified-rate-manager/circuit-breakers` (RBAC `view_system_diagnostics`); UnifiedRateManager pill banner sadece kötü durumda.

---

## Production Hardening Series (May 2026 — DONE)

Full detail → `docs/adr/2026-05-production-hardening.md`.

- **No-Show Terminal-State Guard**: `NON_NOSHOWABLE_STATES`, ikinci no-show 400 + audit_count==1.
- **No-Show Inventory Lock Release**: `handle_no_show` → `release_booking_nights`, INV-6 simetrisi.
- **Closed Folio Refund/Void Guard**: `FolioHardeningService.post_refund/void_charge/void_payment` `folio.status != "open"` iken 4xx.

---

## Production Safety Pack (May 2026 — 8/8 DONE)

Full plan + per-package design notes → `docs/PRODUCTION_SAFETY_PLAN.md`. Pilot operator single entry point → `docs/REPLIT_OPS_CHEATSHEET.md`. **Pre-launch prova rehberi (T-24h → T-1h, 30-60dk):** `docs/PRODUCTION_LAUNCH_REHEARSAL.md` — 9 kapı (Replit Secrets matrix / Sentry UI 11 alarm + Crons / Slack-PagerDuty routing / `rollback.sh --dry-run` / `cm_backlog_alert.py --json` / `verify_atlas_backup.py` / `deploy/smoke.sh` 6/6 / GO/NO-GO HR template doldurma). Sandbox dry-run çıktıları doc'ta referans olarak gömülü (12 May 2026 koşturuldu: rollback fail-mode `.last_good_tag yok` beklenen, cm_backlog `verdict=unknown` sandbox'ta Mongo yok, verify_atlas `api_keys_unset` no-op exit 0).

- **#1 Tek-komut Rollback**: `deploy/rollback.sh` — `last_good_tag`'den önceki başarılı imaj tag'ine döner + `deploy/smoke.sh` otomatik koşar; PASS → tag günceller, FAIL → `.rollback_from` sidecar bırakır. Args: `[tag]`, `--list`, `--dry-run`. `deploy/deploy.sh:170-174` başarılı deploy sonunda `deploy/.last_good_tag`'e yazar. Tam rehber: `docs/ROLLBACK.md` (4 senaryo).
- **#2 Atlas-Managed Backup**: Pilot DB MongoDB Atlas M10+ → continuous backup + PITR + S3 snapshot Atlas managed (yerel mongodump gerek YOK). `backend/infra/atlas_backup_check.py` URI'den `.mongodb.net` algılar; `ATLAS_TIER` env-var ile plan seviyesi. `readiness_validator.py:97-112` Atlas-aware: Atlas+M10+ → `status="atlas_managed", score=1.0`; Atlas+M0+production → `score=0.0`. Opsiyonel snapshot tazelik: `python backend/scripts/verify_atlas_backup.py --max-age-hours 26`. Replit Secrets: `ATLAS_TIER=M10` (zorunlu); `ATLAS_API_*` (opsiyonel snapshot doğrulaması). Restore senaryoları: `docs/ATLAS_BACKUP_AND_RESTORE.md`.
- **#3 CM Observability Single-Source**: Outbox + provider CB görünürlüğü tek helper'dan (`backend/infra/cm_observability_check.py`, public `provider_failover.get_state_counts()` API'si) üç yüzeye yayılır: (1) `/api/health/readiness` `checks.cm_outbox` + `checks.cm_circuit_breakers` (IP/tenant scrub), (2) `python backend/scripts/cm_backlog_alert.py [--json] [--quiet] [--treat-degraded-as-fail] [--sentry-capture]` cron-friendly (exit 0/1/2), (3) mevcut `/api/channel-manager/unified-rate-manager/circuit-breakers` RBAC drill-down. Eşikler: outbox `pending+retry` ≥100 DEGRADED / ≥500 FAIL, `failed` ≥50/≥200, oldest pending ≥600s/≥1800s; CB `open` ≥1 DEGRADED / ≥3 FAIL. Privacy: counts + reasons only, no tenant_id/connection_id/payload. Operatör akışı: `docs/CM_OBSERVABILITY.md`. Tests: `tests/test_cm_observability_check.py` (8 senaryo). **Cron-context Mongo URI gotcha (13 May 2026 rehearsal keşfi)**: `core/database.py:19` `MONGO_URL` env-var arar (default localhost), `backend/start.sh:7-8` Backend için `MONGO_URL=$MONGO_ATLAS_URI` alias yapar. Cron context'te start.sh çalışmaz → `cm_backlog_alert.py main()` başında `os.environ.setdefault("MONGO_URL", os.environ["MONGO_ATLAS_URI"])` fallback'i var (script:172-179). Yeni cron-script eklerken aynı pattern uygulanmalı, aksi halde sessizce localhost'a bağlanır + `verdict=unknown` döner.
- **#4 Sentry Alert Policy + PII Scrub**: Backend SDK `send_default_pii=False` üzerine eklendi: (a) `before_send` PII scrub (`backend/infra/cloud_observability.py:18-93`) — 6 regex (JWT, Bearer/?token=/?api_key=/?secret=, email, IPv4 3. oktet `1.2.3.4 → 1.2.x.4`, MongoDB ObjectId 24-hex), bounded recursion (depth≤6, container≤200), scrub fail olsa event drop edilmez; (b) `cm_backlog_alert.py --sentry-capture` in-process Sentry init, scrub-safe forwarding, FAIL→error/sampler→fatal/DEGRADED→no-send; (c) Tag taxonomy zorunlu: `subsystem` (auth/rls/hotelrunner/exely/cm-backlog/cm-circuit/atlas-backup/kvkk/outbox/payment/night-audit) + `severity` (info/warning/error/fatal); `tenant_id`/`property_id` ASLA tag olarak set edilmez. Replit Secrets: `SENTRY_ENVIRONMENT=pilot`. Tam routing tablosu (11 alarm), severity matrix, manuel Sentry-UI kurulum: `docs/SENTRY_ALERT_POLICY.md`.
- **#5 Admin Sistem Sağlığı — Pilot Section**: `frontend/src/pages/SystemHealthDashboard.jsx`'a "Pilot Production Safety" section eklendi (Genel durum şeridi ↔ KPI satırı arası). Tek endpoint: `axios.get('/production-golive/readiness')` (Promise.allSettled 13. çağrı). 5 KpiCard: Readiness Verdict / CM Outbox / Circuit Breakers / Atlas Backup / Observability (`sentry_active` + `otel_active` root scalar field'lar — nested DEĞİL). Header'da 3 doc tooltip path. IIFE pattern + nullable-safe (state null ise section gizli, error state YOK). Mevcut UI sıfır kırılma.
- **#6 Kill-Switch / Feature Flag Standardı**: Helper `backend/infra/feature_flags.py` — `is_enabled` / `is_disabled` / `production_guard(flag, allowed_envs={dev,test,sandbox,ci,local})` / `snapshot()`. Tutarlı parser (`1/true/yes/on/y/t`); bilinmeyen token → WARNING + default. `production_guard` güvenlik bypass'ı prod'da YOKSAYILIR + WARNING. `snapshot()` privacy-safe (raw env value YOK); `requested != active` farkı leak'i fark ettirir. `KNOWN_FLAGS` tuple = mevcut 5 kill-switch (kod ↔ doc lock-step). Operatör doc'u: `docs/KILL_SWITCH_REGISTRY.md` — naming standardı, mevcut envanter, 6 önerilen yeni flag (DEFER). Bu tur **standart-belirleme** turu — mevcut 5 call site (`expo_push.py:60`, `auth_throttle.py:161`, `auth.py:134`, `quick_id_proxy.py:32`, `security_ops_router.py:126`) migrate EDİLMEDİ; ileri turlarda PR per call site.
- **#7 Pilot İlk 24h İzleme Runbook**: `docs/PILOT_FIRST_24H_MONITORING.md` — operatör nöbet defteri. Tasarım: zaman bantlarına göre azalan frekans (T+0→T+15dk her 5dk; T+15dk→T+1h her 15dk; T+1h→T+6h her 30dk; T+6h→T+24h her 2sa). Bölümler: yoğun bakım + akut faz + stabilizasyon + sürekli izleme + eşik tabloları (ROLLBACK derhal: 5xx>50%, login %0, folio loss, Mongo pool exhausted, PII leak / Sadece izle: tek CB OPEN, outbox 50-100, P95 2-3sn) + operasyon defteri şablonu + tatbikat modu + T+24h sonrası transition.
- **#8 Replit OPS Cheat-Sheet**: `docs/REPLIT_OPS_CHEATSHEET.md` — pilot 24/7 nöbet için tek-sayfa operatör referansı. Tasarım: "30 saniyede cevap" — §0 acil durum kısayolu (`bash deploy/rollback.sh`), §1 health endpoint matrisi, §3 sorun→triage akışı (9 belirti + 5dk karar matrisi), §4 yaygın senaryolar, §5 eskalasyon, §6 alfabetik komut listesi, §8 Replit-spesifik notlar (workflow restart, secrets vault GUI ASLA terminal, `/tmp/logs/<workflow>_*.log`). §7 çapraz-link 9 runbook.

---

## F8 Stress Test Series

Tek doğruluk kaynağı: `docs/STRESS_TEST_ROADMAP.md`. Faz başına ADR yolu aşağıda; mutlak kurallar her fazda aynı: pilot mutation yok, `external_calls=[]`, `failedTests=0`, `P0=P1=0`, verdict ≥ GO WITH WATCH. Ortak helper'lar (`frontend/e2e-stress/fixtures/stress-helpers.js`) — `(testInfo, module, ...)` konvansiyonu: `assertPilotDriftZero`, `assertPiiMasked`, `withModuleProbe`, `callTimed`/`callTimedWithBackoff`. Reporter modül aggregation dinamik (rec annotation `module` field).

### F8A — Front Office / Folio / Housekeeping / Reservation Lifecycle / Night Audit (DONE pending CI #47)

`docs/adr/2026-05-f8a-stress-evolution.md` — 4 spec × ~30 test + v2 push (2 yeni spec + 3 yeni test), 500-oda stress tenant. Day-turnover / room-move / folio-mass / housekeeping-mass + reservation lifecycle (create/modify/cancel/no-show/overbooking/group/multi-room) + night-audit (business-date/run/idempotency/exceptions) + open-folio refund/void.

**Tur tarihçesi**: tur-20 RNL leak fix (checkout transaction'ında `release_booking_nights`), tur-21 perf fix (release call transaction içine), tur-22 OOO TOCTOU fix (`check_in_booking_atomic` + V1 `room_move` atomic CAS, `out_of_service` ROOM_BLOCKED_STATUSES'a eklendi). **tur-27 spec resilience**: (a) `callTimed`/`callTimedWithBackoff` `opts.timeout` desteği (heavy endpoint override), (b) 06-A NA `test.setTimeout(180s)` + per-call 120s + `status=0`→REVIEW+P1, (c) 04-C4 void `pickChargeId` field-name drift fallback + `allNoCharge`→REVIEW+P2 + `detail_shape/charge_shape` diagnostic, (d) 05-A reservation create `first_fail_body` snapshot + `all_403`/`all_404`→REVIEW+P2 + fail_modes assert message'a dahil. **tur-29 (CI #45 NO-GO)**: per-batch delta ÇALIŞTI, cascade YOK, ama 20 izole P0 göründü. Architect 3-iter review final fix: endpoint-level **per-source structural collapse** — CM gate `cm_connectors_lookup_ok && count==0 && !CM_PARTNER_WEBHOOK_URL_env` (raw env, module import değil); Afsadakat gate `afsadakat_tenants_lookup_ok && active_tenants_count==0`. Symmetric TRUE fail-open: her lookup exception → `lookup_ok=False` → gate False. Response additive: `inert_calls_filtered_by_no_connectors` + `structural_breakdown` per-source flags. **tur-29e (CI #46 NO-GO)** root cause: message-pattern eksikliği; `EventSyncService.handle_event` 0-connector durumda `{handled: True, sync_jobs_created: 0}` döner, dispatcher line 100'e düşüp `delivery_message="Dispatched: 0 sync jobs created"` yazar — mevcut `inert_patterns` yakalamıyordu. Fix: pattern set genişletildi (`"dispatched: 0"`, `"no webhook url configured"`, `"missing creds"`). Env'den bağımsız. Structural-collapse layer defense-in-depth olarak korundu.

**F8A v2 backlog**: CM outbox event consistency F8L'e devredildi (geri kalan tüm maddeler kapatıldı).

### F8B — Guest Experience (GO WITH WATCH after tur-26)

`docs/adr/2026-05-f8b-stress-evolution.md` — 4 spec (10/11/12/13), 22 test, QR/complaints/messaging yüzeyleri. Seed: `_build_f8b_docs` (room_qr_requests + service_complaints + messages + notifications). Dry-run guarantees: complaint `guest_id=None` → Resend silent; messaging sadece `/api/messaging/send-*` (legacy provider'a dokunmaz); folio adjustment lokal. Helper: `callTimedWithBackoff` (429 retry, fallbackSleepMs cap 15s). Workflow timeout 15→30dk.

### F8C — MICE / Event / Banquet / Group (DONE — GO WITH WATCH after tur-5, 2026-05-18)

`docs/adr/2026-05-f8c-stress-evolution.md` — 4 spec (14/15/16/17), 19-23 test, MICE & sales yüzeyleri. Seed: `_build_f8c_docs` (8 spaces + 30 events status=lead + 30 opportunities + 20 leads + 10 competitors + 3 packages). Dry-run invariants: events `definite` max (`completed` → folio post + bus.publish), opportunities lead→qualified→proposal→contract (won/lost yok). **module-blocked pattern** (tur-4 15-spec / tur-5 14-spec): endpoint 403 veya cache-stale ise `moduleBlocked=true` + P2 informational + A/B/C/D `test.skip()`, pilot_drift (E) çalışmaya devam — backend RBAC/cache durumları kasıtlı, spec resilience tercih edildi.

### F8D — HR / Staff / Shift / Leave / Department (DONE — GO WITH WATCH, CI yeşil, 2026-05-18)

`docs/adr/2026-05-f8d-hr-staff-shift-evolution.md` — 4 spec (20/21/22/23), 19 test. Seed: `_build_f8d_docs` (5 dept + 8 pos + 30 staff + 30 leave_balance + 60 attendance + 20 shift + 5 leave_req + 5 swap + 3 perf). Dry-run guarantees: notifications in-app only (F8B cleanup kapsar), payroll `/finalize` ASLA çağrılmaz (live workflow için), attendance seed CLOSED (`clock_out` set) → spec clock-in yeni OPEN row açabilir, dept code prefix-isolated. **module-blocked + RBAC short-circuit** desen (F8C 14/15 mirror): `permFail === N` veya pool eksik ise P2 informational + A/B/C `test.skip()`, D pilot_drift bağımsız. STRESS_COLLECTIONS'a 10 yeni koleksiyon (payroll_records dahil — forward-compat orphan scrub).

**F8D v2 backlog**: perf-review lifecycle, payroll dry-run (finalize ASLA), org chart traversal, shift conflict/coverage, leave accrual, HR audit log, cross-dept RBAC, PII guard.

### F8D-v3 — HR Coverage Extension (2026-05-22, 6 yeni spec)

Murat audit önerilerine göre eklendi: spec 38 (employee profile aggregate + cross-tenant IDOR), 38B (staff self-service `/payroll/me` locked-only + cross-staff IDOR matrix), 39 (dept/position CRUD + FK guard + sync-from-staff idempotency), 39B (offboarding read-only + cross-tenant terminate guard — stress staff ASLA terminate edilmez P0 invariant; preconditioned 409 outstanding-equipment guard: assign synth equipment → sanity verify → terminate probe 409 guaranteed → return equipment → verify staff still active; precondition fail → SKIP), 35B (coverage-rules CRUD + min_staff validation), 33B (payroll export JSON/CSV/XLSX PII scan TC/IBAN/JWT — context-aware TC `identity_no/tc_kimlik` field P0 vs bare 11-digit P2 informational; IBAN TR + spaced/hyphenated 26-char; JWT Bearer-prefixed VEYA bare three-segment; CSV column-aware TC; + cross-tenant XLSX IDOR real pilot run_id harvested via pilot_token + anonymous reject). Backend endpoint'leri Task #264-#270 ile zaten mevcut; specs read-only/safe-probe doctrine kullanır. CI verify bekleniyor.

### F8E — Finance / Cashier / Accounting / Invoice / City Ledger (DONE v2 — GO WITH WATCH CI #42+ bekleniyor, 2026-05-19)

`docs/adr/2026-05-f8e-finance-stress-evolution.md` — 5 spec (24/25/26/27/**28**), 24 test (4 D-extension + 4 spec 28), cashier shift lifecycle + city-ledger + accounting CRUD + finance reports (VAT/P&L/balance-sheet/dashboard/cash-flow) + currency lifecycle (rates+convert).

**v2 push notları**: spec 28 RBAC-tolerant (hard floor = no-perm yüzeyler: VAT + currencies + cash-flow), `view_finance_reports` gate'li reports super_admin geçer ama perm_gated_fails ayrı raporlanır. E-fatura paths (`/efatura/*`, `/invoices/{id}/generate-efatura`) **YASAK** (gerçek GİB dispatch); bilinçli dışarıda. STRESS_COLLECTIONS += `currency_rates` (tenant-scoped orphan scrub). Seed: `_build_f8e_docs` (3 closed shift + 30 cashier_txn + 10 supplier + 20 expense + 10 invoice + 5 bank_acc + 15 item + 10 stock_movement + 20 cash_flow + 5 city_ledger). Dry-run guarantees: open-shift seed YOK (`uniq_tenant_open_shift` partial index ihlali olmasın), Iyzico router seviyesinde tetiklenmiyor, folio_id + open shift gerektiren split-payment / mobile record-payment spec'lerde çağrılmıyor. **module-blocked + RBAC short-circuit** (F8C/D mirror): `permFail === N` veya endpoint non-2xx ise P2 informational + A/B `test.skip()`, C pilot_drift bağımsız. STRESS_COLLECTIONS'a 11 yeni koleksiyon (`city_ledger_transactions` seed yok ama scrub var — forward-compat).

### F8I — Admin / RBAC / Settings / Audit (Task #193 DONE 2026-05-19)

2 spec (30-admin-rbac + 31-settings-audit), 13 test. Spec 30: super_admin baseline + per-role test user create (front_desk/housekeeping/finance/sales via `/api/admin/tenants/{stress_tid}/team` POST) + login + negative matrix (10 hassas endpoint × 4 rol = 40 auth check) + existence-disclosure (bogus UUID lookup) + idempotent cleanup (audit_logs ASLA silinmez, KVKK). Spec 31: tenant info PATCH (description marker prefix-tagged) + audit/timeline reachability + PII guard + cross-tenant settings drift gate (pilot tenant info baseline'a göre ZERO drift, marker leak P0) + RL boundary (20x ardışık GET, 5xx=0) + restore-on-cleanup. Module-blocked: super_admin team POST veya admin tenants probe non-2xx → moduleBlocked + P2 informational + A/B/C/D skip; D/F (pilot_drift + external_calls) BAĞIMSIZ.

### F8L — CM Webhooks + Outbox (Task #195 IN_PROGRESS 2026-05-19)

3 spec (50-cm-webhooks-exely + 51-cm-hotelrunner-outbox + 52-cm-outbox-idempotency), 20 test (architect-iter-4 sonrası: 50-F readiness gate + 50-G valid-payload duplicate ingest + 50-H cancel idempotency + 51-F signed valid-path + 52-E active idempotency + spec 52 BASE const runtime fix; conditional path'lerde REVIEW+P2 informational, secret/whitelist mevcutsa P0/P1 enforce).

**Spec 50 (Exely `/api/webhooks/exely`)**: /health + /info reachability + auth-mode classification (fail_closed_503 / ip_gated_403 / open_for_testing) + auth contract probes (empty body / garbage XML / wrong Content-Type / JSON-on-XML — 2xx kabul=P0, mode-mismatch=P1) + payload-size limit (512 KiB → 400/413/503/403, 2xx=P0) + tenant injection probe (pilot_tid forge XML payload — fail_closed/ip_gated mode'da 2xx=P0) + replay burst (5 ardışık POST, 5xx storm=P1) + PII/token guard /info response.

**Spec 51 (HotelRunner `/api/channel-manager/hotelrunner`)**: logs/events JWT-auth probe + sig-mode classification (fail_closed_503 / sig_required_401 / open_for_testing) + sig contract (6 probe: no headers, sig-only, ts-only, stale ts, bad sig, invalid ts format — fail_closed/sig_required mode'da 2xx=P0) + webhook surface coverage (reservations/modifications/cancellations 3 endpoint aynı kontrat, drift=P1) + tenant injection forge + logs/events + logs/errors cross-tenant scope + PII/token guard.

**Spec 52 (Outbox + Conflict Queue)**: /api/outbox/status pilot super_admin reachability + t1/t2 delta no-op window (pending/processing/retry/failed delta>0=P2) + /api/outbox/events PII+token guard + stres-token RBAC bypass (2xx=P0 require_super_admin guard) + /api/channel-manager/conflict-queue/count + /conflict-queue stres scope (pilot booking ID/tid leak=P0) + anonymous reachability (2xx=P0) + PII+token guard.

Module-blocked doctrine: her spec'te setup probe non-2xx → moduleBlocked + P2 informational + A/B/C/D skip; E (50/51) ya da D (52) pilot_drift+external_calls bağımsız. Spec auth-mode aware — EXELY_IP_WHITELIST/HOTELRUNNER_WEBHOOK_SECRET stres ortamında set olmayabilir; 503 fail-closed contract PASS sayılır.

### F8M — GraphQL + B2B API (Task #194 DONE 2026-05-19)

2 spec (40-graphql-tenant-isolation + 41-b2b-api-key-scope), 11 test.

**Spec 40**: GraphQL POST `/api/graphql` reachability probe + introspection policy (open → P2 informational) + Mutation surface contract (schema'da Mutation YOK; görünürse P2) + resolver isolation (bookings/rooms/dashboard/nested — pilot REST'ten alınan sample booking/guest/room ID stress response'unda görünürse P0) + cross-tenant injection probes (5 probe: guest_id spoof, room_id spoof, big-skip pagination, negative skip, variable collision `$tid`) + auth boundary (no-auth + invalid JWT + pilot self-query aggregation şüphesi P1) + PII guard (nested Guest tipi `phone/email/idNumber` masked olmalı) + token leak guard.

**Spec 41**: agencies probe + idempotent pre-cleanup + POST `/api/b2b/api-keys?agency_id=<stress_agency>` raw key alıp `createdRawKey` + lifecycle smoke (GET info → has_key:true, key_prefix masked, raw key body'de yoksa P0) + scope assertions (X-API-Key header wrapper `callApiKey`; missing/garbage 401-403, valid 2xx veya 404=REVIEW; cross-tenant wake-up-calls pilot_tid leak guard) + revoked-key contract (DELETE → smoke 401/403, hala kabul ediliyorsa P0) + existence-disclosure (bogus UUID + cross-tenant pilot agency GET; has_key:true ise P0) + invariants + `afterAll` belt-and-suspenders DELETE.

Module-blocked: GraphQL probe non-2xx veya agency listesi/key create non-2xx → moduleBlocked + A/B/C/D skip; E pilot_drift+external_calls bağımsız. Schema (`backend/graphql_api/schema.py`) yalnız Query — Mutation YOK; B2B api-keys CRUD JWT auth `view_system_diagnostics` perm gerektirir, raw key sadece create response'unda döner.

### Stress Roadmap sync (2026-05-22)

`docs/STRESS_TEST_ROADMAP.md` faz tablosu disk'teki 56 spec dosyasına göre yeniden senkronize edildi. F8F/G/H/K önceden "Planlandı" görünüyordu → DONE (real specs 70/71/80/90/60/61/62). F8L önceki "IN_PROGRESS" stale idi → DONE. F8O dosya 44 disk'te → DONE. F8Q (18/45/63/97) DONE (commit `3f49b966`). Eski "F8F–F8N expansion contract" tablosu LEGACY PLANNING olarak işaretlendi (çelişki = üst tablo bağlayıcı). Yeni "Hardening Backlog (F8R+)" bölümü: export-artifact-IDOR, file-upload-security, staff-self-service, auth-token-lifecycle, ws-isolation, ops-readiness-smoke, e-fatura-forbidden, AI prompt PII, QR rotation deep, warehouse-transfer.

### Full Stress Suite F8A–F8N — Yeşil Baseline

F8A–F8E + F8I yeşil baseline (27 spec, 173+ test); F8F/G/H/J/K/L/M/N planlı/done (Task #194-#201). Yüksek risk yüzeyleri: public/KVKK (F8K), CM webhook (F8L), GraphQL/B2B (F8M), RBAC (F8I).
