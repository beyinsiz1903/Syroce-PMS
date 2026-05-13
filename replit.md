# Syroce PMS

An enterprise-grade, multi-tenant Hotel Property Management System with AI-powered features adaptable to any accommodation type.

## Run & Operate

- **Frontend**:
  - Install dependencies: `cd frontend && yarn install`
  - Start dev server: `cd frontend && yarn run start`
  - Build for deployment: `cd frontend && yarn build`
- **Backend**:
  - Start services (MongoDB, Redis, FastAPI): `bash backend/start.sh`
- **Environment Variables**: `JWT_SECRET`, `RESEND_API_KEY`, `SENTRY_DSN`, `VITE_SENTRY_DSN`, `QUICKID_SERVICE_KEY`, `QUICKID_URL`, `ENABLE_QUICKID_DEMO`, `ROOM_QR_SECRET`, `PUBLIC_APP_URL`, `AFSADAKAT_BASE_URL`, `AFSADAKAT_ADMIN_TOKEN`, `ENABLE_SETUP_ENDPOINTS`, `SETUP_SECRET`, `EXELY_IP_WHITELIST`, `EXELY_TRUST_FORWARDED`, `EXELY_TRUSTED_PROXY_IPS`, `JWT_EXPIRATION_MINUTES`, `REFRESH_TOKEN_EXPIRATION_DAYS`, `DISABLE_EXPO_PUSH`, `MOBILE_PUSH_SCAN_SECONDS`, `MOBILE_PUSH_VIP_WINDOW_MINUTES`, `KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`, `ATLAS_TIER`, `SENTRY_ENVIRONMENT`.

## Stack

- **Frontend**: React 19, Vite 8, Tailwind CSS, shadcn/ui, TanStack Query v5, React Router v7, i18next, Yarn 1.22.22, Vitest.
- **Backend**: FastAPI (Python 3.11+), MongoDB 7.0+ (motor), Redis, Celery, pytest.
- **Auth**: JWT, AES-256-GCM, RBAC.

## Where things live

- `frontend/`: React + Vite application.
- `backend/`: FastAPI Python application (contains `bootstrap/`, `channel_manager/`, `controlplane/`, `core/`, `domains/`, `modules/`, `workers/`).
- `infra/`: Prometheus/Grafana/K8s config.
- `deploy/`: Deployment scripts (`rollback.sh`, `smoke.sh`, `deploy.sh`).
- `docs/`: ADRs and playbooks (pilot operator entry point: `docs/REPLIT_OPS_CHEATSHEET.md`).
- **Key Files**:
  - DB Schema: `backend/models/schemas/` (Pydantic models).
  - API Contracts: `backend/routers/`, `backend/domains/*/router.py`.
  - Theme Files: `frontend/tailwind.config.js`.

## Architecture decisions

- **Multi-tenant Architecture**: Isolated data sets per hotel enforced by `tenant_id` scoping.
- **Property Type Profiling System**: Dynamic configuration of modules and features based on property type.
- **Atomic Operations**: Critical workflows use MongoDB transactions or unique compound indexes for atomicity.
- **Security-First Development**: Robust defenses against common web vulnerabilities.
- **Event-Driven Integrations**: Syroce Xchange (SXI) bus for reliable, idempotent event distribution with SSRF protection.
- **Fail-Closed Principle**: Security-critical configurations default to fail-closed, preventing insecure operation if not properly configured.

## Product

- **Core PMS**: Front desk, reservations, housekeeping, financial folios, guest management.
- **AI Integration**: Upsell offers, dynamic pricing, forecasting, no-show risk, guest pattern analysis.
- **Channel Management**: Unified Rate Manager, OTA sync (Exely, HotelRunner), SXI bus.
- **Financial Operations**: Cashier module, PCI-DSS, automated Turkish Accommodation Tax, Procurement.
- **Guest Experience**: Room QR requests, guest reviews & NPS, digital key, mobile apps.
- **Operational Efficiency**: Spa & MICE, shift handover, in-app help, regulatory reports.
- **Security & Compliance**: 2FA/TOTP, KVKK/GDPR, audit logging, Quick-ID.

## User preferences

_Populate as you build_

## Gotchas

### Testing

- **UI Business E2E Suite (May 2026)**: `frontend/playwright.business.config.js` + `frontend/e2e-business/` (smoke ile birlikte yaşar, ayrı klasör). Komut: `cd frontend && yarn test:e2e:business` (`:list` ile dry-enumerate). Env zorunlu: `E2E_BASE_URL`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD` (config fail-fast). Pilot/staging'e koşar; **dış servisler (gerçek payment / OTA push / SMS / e-posta / KVKK)** spec içinde `SKIP/REVIEW` olarak işaretli — asla canlıya etmez. 20 spec dosyası (01-20), kapsam-bazlı: auth-nav / dashboard-health / reservation / checkin-checkout / folio / invoice / mice / housekeeping / guest-crm / users-roles / channel-manager / rate-inventory / payments / reports / notifications / settings / audit-log / security-rbac / responsive / recap. Adım sayacı: PASS/FAIL/REVIEW/SKIP — `fixtures/recorder.js:rec(testInfo, {module, scope, step, status, endpoint, http, note})` annotation ile kayıt. **Auth flow**: `global-setup.js` bir kez UI login yapar → `e2e-business/.auth/admin.json` storageState; `/api/auth/login` ile bearer token cache → `e2e-business/.auth/token.json` (api fixture okur). **Test data**: `factory.*` E2E_<ts36>_KIND prefix; `trackEntity({kind, id, label, cleanup})` registry → reporter'da inventory tablosu. **Soft-fail**: feature/page yoksa REVIEW (FAIL değil) — pilot dataset boş olabilir. **Custom reporter** `markdown-reporter.mjs` → `docs/drill_reports/YYYYMMDD_full_ui_business_e2e.md` (yönetici özeti / modül tablosu / kritik FAIL / test verisi / REVIEW+SKIP / risk P0-P3 / GO|GO-WITH-WATCH|NO-GO). HTML: `frontend/playwright-business-report/`; trace+video+screenshot: `frontend/test-results-business/`. **Gotcha**: spec'lerden import edilen helper'lar Playwright transform ile CJS'e dönüştüğü için `import.meta.url` kullanılmaz — yerine `process.cwd()` (Playwright koşumunda `frontend/` döner) kullanıldı (`fixtures/data-factory.js`, `fixtures/api.js`, `global-setup.js`). Reporter `.mjs` çünkü Playwright reporter'ı `require()` ile yükler ve package.json'da `"type": "module"` yok.
- **UI E2E Smoke Suite (May 2026)**: `frontend/playwright.smoke.config.js` + `frontend/e2e-smoke/` (mevcut `frontend/e2e/` happy-path suite'inden ayrı, çakışmaz). Komut: `cd frontend && yarn test:e2e:smoke`. Env zorunlu: `E2E_BASE_URL`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD` (hardcoded fallback YOK — `fixtures.js:requireEnv` eksikse fail-fast). 24 route × 2 project (`desktop` 1440×900 + `mobile` Pixel 7) = 48 test. **Critical** (17 route, fail = suite FAIL): Dashboard, Sistem Sağlığı, Channels Hub/CM Dashboard/Unified Rate Manager/Channel Connections/Ops/Conflict Queue (`/channels?tab=conflicts`), Rezervasyon Takvimi/PMS/PMS Operasyonlar, Folio/Grup Folio, Admin Control Panel/Kullanıcı-Rol (`/admin/user-roles`), Ayarlar, Güvenlik. **Secondary** (7 route, soft warning): Control Plane, Audit Timeline, Rate Manager, İK, Tedarik Pazarı, Satınalma. Her route için: navigate → boş ekran/404/500/Error UI tespit (`inspectPageContent`) + console error + network 4xx/5xx (allowlist'li: i18next/Sentry beacon/health probe 503 vb.) + güvenli buton tıklama (yalnız `Yenile`/`Refresh`/`Ara`/`Search` regex; destructive blacklist: sil/iptal/refund/void/vardiya kapat/çıkış). **Çıktı**: HTML report `frontend/playwright-smoke-report/` + custom Markdown reporter `docs/drill_reports/YYYYMMDD_ui_e2e_smoke.md` (özet + failed steps + tüm route matrisı + safe-click özeti + artifact path'leri) + trace/video/screenshot `frontend/test-results-smoke/`. Catalog: `frontend/e2e-smoke/routes.js` (`ROUTES` + `CONSOLE_ERROR_ALLOWLIST` + `NETWORK_ERROR_ALLOWLIST`).

### Conventions (always-on rules)

- **API Call Conventions**: Use relative paths WITHOUT `/api/` for `axios` calls; use `/api/` explicitly for native `fetch`.
- **Color Palette Convention**: Migrate from `purple-*` to `indigo-*` and `orange-*` to `amber-*` for Tailwind classes. Do not use `purple` or `orange` for new code.
- **In-App Dialog System**: Use `frontend/src/lib/dialogs.js` Promise API (`confirmDialog/alertDialog/promptDialog`) instead of native `window.alert/confirm/prompt`.
- **Walk-in Placeholder Guest Names**: API responses replace placeholder names (e.g., "C4", "X") with `Walk-in Misafir #XXXX` while preserving original DB values.
- **Image Uploads**: Strict validation for type, size, and dimensions.
- **Outbound HTTP Calls**: Tenant-configurable outbound URLs are protected with DNS-rebinding-safe transport, IP allowlisting, and transport pinning.

### Auth, security & infra

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

### Design system & layout

- **Sprint A Design System (May 2026)**: Use `<PageHeader icon title subtitle actions>` (`frontend/src/components/ui/page-header.jsx`) for page tops; `<KpiCard icon label value sub intent highlight active onClick>` (`frontend/src/components/ui/kpi-card.jsx`) for KPI grids — `intent` palette: `info` (sky), `success` (emerald), `warning` (amber), `danger` (rose), `neutral` (slate), `default`. Interactive KpiCard auto-adds `role=button + tabIndex=0 + Enter/Space + focus-visible`. Use `<StatusBadge intent icon>` (`frontend/src/components/ui/status-badge.jsx`) for status pills (same palette). Standards: Yenile button always `<Button variant="outline" size="sm"><RefreshCw className="w-4 h-4 mr-1.5"/>Yenile</Button>`; primary CTA = default Button (siyah dolu) — gradient/blue/green özel renk YOK; emoji yok. **İSTİSNA**: ReservationCalendar "Rezervasyon ekle" butonu **bilinçli** amber kaldı (en sık kullanılan marka aksiyonu). Para birimi: `formatCurrency(amount, currency || 'TRY')` from `frontend/src/lib/currency.js`. Tarih lokali: takvim gün kısaltmaları `Pzt/Çar`, date range `month: 'long'` (Mayıs). 12 pilot pages migrated (DepartureList/NoShowToday/WakeUpCalls/LostFound/DepositTracking/ArrivalList/Housekeeping/Maintenance/NightAudit/FrontdeskAudit/RMSModule/Mailing); Yenile butonu `?refresh=1` ile cache_manager `_nocache` kwarg'ını tetikler.
- **Pages Layout Wrap (Current Default — M5, May 2026)**: Routes own the Layout sarımı, NOT pages. Add `wrapLayout: true, layoutModule: "..."` to the route entry in `frontend/src/routes/routeDefinitions.jsx`; the page returns just its content (no `import Layout`, no `<Layout>` JSX). **Önemli**: `layoutModule` değeri NAV_ITEMS'daki gerçek `key` ile eşleşmeli — boş veya yanlış key ("dashboard" gibi placeholder) bırakılırsa standalone "Kontrol Paneli" butonu sürekli aktif görünür ve üst menüde aynı anda iki sekme mavi çıkar. 118/123 pages migrated via `tools/codemod-layout/codemod.mjs`; 11 intentionally retain in-page `<Layout>` (6 use `MaybeLayout` for hub embed, 4 imported but never routed, 1 `ReservationCalendar.jsx` returns two distinct `currentModule` values conditionally). **Regression guard**: `cd frontend && yarn guard:layout` (or `node tools/codemod-layout/guard.mjs`) fails if any route with `wrapLayout: true` points to a page that still imports `Layout` — prevents double-wrap.

### CM-Hardening Series (May 2026 — DONE)

Full architecture, test pins, file/line references → `docs/adr/2026-05-cm-hardening.md`.

- **Turu #1a/#1b/#1c/#2**: Overbooking alert emission + Conflict Queue API + UI + Bulk Resolve. HotelRunner provider'da transactional booking metodu YOK (cancel bile inventory recompute kullanır).
- **Turu #3a/#3b**: No-Show OTA Outbox Parity (event production + HotelRunner inventory recompute, Strategy A). `outbox_dispatcher.EVENT_TYPE_TO_CM_EVENT["booking.no_show.v1"] = "booking_no_show"`.
- **Turu #3c (DEFERRED, Discovery Complete)**: Exely no-show parity gap — repo'da iki paralel CM modülü ve farklı `ConnectorProvider` enum'ları (`channel_manager/domain/models/connector_account.py:18` HOTELRUNNER/SITEMINDER/CHANNEX vs `domains/channel_manager/data_model.py:29` HOTELRUNNER/EXELY). Exely conn'lar ayrı `exely_connections` koleksiyonunda → `EventSyncService` boş liste döner → outbox sessizce yutar. Pilot'ta Exely müşterisi yok, periyodik `exely_pull_worker.py` (180s) gap'i kapsıyor. Strategy A (~4-6h, ÖNERİLEN) vs Strategy B (~1-2g, full unification) — ADR'de tam akış haritası.
- **Turu #4 (Stop-Sale Circuit Breaker)**: `provider_failover.CircuitBreaker` HR `push_daily_inventory`+`push_date_range_inventory` ve Exely `push_ari` etrafında sarıldı. Per-connection key (`hotelrunner:{conn_id}` / `exely:{conn_id}`). Defaults: `failure_threshold=5`, `recovery_timeout=60s`, `half_open_max_calls=3`. Breaker OPEN iken `ProviderResult(success=False, error_type="CircuitOpen", metadata.circuit_open=True)`. UI: `GET /api/channel-manager/unified-rate-manager/circuit-breakers` (RBAC `view_system_diagnostics`); UnifiedRateManager pill banner sadece kötü durumda.

### Production Hardening Series (May 2026 — DONE)

Full detail → `docs/adr/2026-05-production-hardening.md`.

- **No-Show Terminal-State Guard**: `NON_NOSHOWABLE_STATES`, ikinci no-show 400 + audit_count==1.
- **No-Show Inventory Lock Release**: `handle_no_show` → `release_booking_nights`, INV-6 simetrisi.
- **Closed Folio Refund/Void Guard**: `FolioHardeningService.post_refund/void_charge/void_payment` `folio.status != "open"` iken 4xx.

### Production Safety Pack (May 2026 — 8/8 DONE)

Full plan + per-package design notes → `docs/PRODUCTION_SAFETY_PLAN.md`. Pilot operator single entry point → `docs/REPLIT_OPS_CHEATSHEET.md`. **Pre-launch prova rehberi (T-24h → T-1h, 30-60dk):** `docs/PRODUCTION_LAUNCH_REHEARSAL.md` — 9 kapı (Replit Secrets matrix / Sentry UI 11 alarm + Crons / Slack-PagerDuty routing / `rollback.sh --dry-run` / `cm_backlog_alert.py --json` / `verify_atlas_backup.py` / `deploy/smoke.sh` 6/6 / GO/NO-GO HR template doldurma). Sandbox dry-run çıktıları doc'ta referans olarak gömülü (12 May 2026 koşturuldu: rollback fail-mode `.last_good_tag yok` beklenen, cm_backlog `verdict=unknown` sandbox'ta Mongo yok, verify_atlas `api_keys_unset` no-op exit 0).

- **#1 Tek-komut Rollback**: `deploy/rollback.sh` — `last_good_tag`'den önceki başarılı imaj tag'ine döner + `deploy/smoke.sh` otomatik koşar; PASS → tag günceller, FAIL → `.rollback_from` sidecar bırakır. Args: `[tag]`, `--list`, `--dry-run`. `deploy/deploy.sh:170-174` başarılı deploy sonunda `deploy/.last_good_tag`'e yazar. Tam rehber: `docs/ROLLBACK.md` (4 senaryo).
- **#2 Atlas-Managed Backup**: Pilot DB MongoDB Atlas M10+ → continuous backup + PITR + S3 snapshot Atlas managed (yerel mongodump gerek YOK). `backend/infra/atlas_backup_check.py` URI'den `.mongodb.net` algılar; `ATLAS_TIER` env-var ile plan seviyesi. `readiness_validator.py:97-112` Atlas-aware: Atlas+M10+ → `status="atlas_managed", score=1.0`; Atlas+M0+production → `score=0.0`. Opsiyonel snapshot tazelik: `python backend/scripts/verify_atlas_backup.py --max-age-hours 26`. Replit Secrets: `ATLAS_TIER=M10` (zorunlu); `ATLAS_API_*` (opsiyonel snapshot doğrulaması). Restore senaryoları: `docs/ATLAS_BACKUP_AND_RESTORE.md`.
- **#3 CM Observability Single-Source**: Outbox + provider CB görünürlüğü tek helper'dan (`backend/infra/cm_observability_check.py`, public `provider_failover.get_state_counts()` API'si) üç yüzeye yayılır: (1) `/api/health/readiness` `checks.cm_outbox` + `checks.cm_circuit_breakers` (IP/tenant scrub), (2) `python backend/scripts/cm_backlog_alert.py [--json] [--quiet] [--treat-degraded-as-fail] [--sentry-capture]` cron-friendly (exit 0/1/2), (3) mevcut `/api/channel-manager/unified-rate-manager/circuit-breakers` RBAC drill-down. Eşikler: outbox `pending+retry` ≥100 DEGRADED / ≥500 FAIL, `failed` ≥50/≥200, oldest pending ≥600s/≥1800s; CB `open` ≥1 DEGRADED / ≥3 FAIL. Privacy: counts + reasons only, no tenant_id/connection_id/payload. Operatör akışı: `docs/CM_OBSERVABILITY.md`. Tests: `tests/test_cm_observability_check.py` (8 senaryo). **Cron-context Mongo URI gotcha (13 May 2026 rehearsal keşfi)**: `core/database.py:19` `MONGO_URL` env-var arar (default localhost), `backend/start.sh:7-8` Backend için `MONGO_URL=$MONGO_ATLAS_URI` alias yapar. Cron context'te start.sh çalışmaz → `cm_backlog_alert.py main()` başında `os.environ.setdefault("MONGO_URL", os.environ["MONGO_ATLAS_URI"])` fallback'i var (script:172-179). Yeni cron-script eklerken aynı pattern uygulanmalı, aksi halde sessizce localhost'a bağlanır + `verdict=unknown` döner.
- **#4 Sentry Alert Policy + PII Scrub**: Backend SDK `send_default_pii=False` üzerine eklendi: (a) `before_send` PII scrub (`backend/infra/cloud_observability.py:18-93`) — 6 regex (JWT, Bearer/?token=/?api_key=/?secret=, email, IPv4 3. oktet `1.2.3.4 → 1.2.x.4`, MongoDB ObjectId 24-hex), bounded recursion (depth≤6, container≤200), scrub fail olsa event drop edilmez; (b) `cm_backlog_alert.py --sentry-capture` in-process Sentry init, scrub-safe forwarding, FAIL→error/sampler→fatal/DEGRADED→no-send; (c) Tag taxonomy zorunlu: `subsystem` (auth/rls/hotelrunner/exely/cm-backlog/cm-circuit/atlas-backup/kvkk/outbox/payment/night-audit) + `severity` (info/warning/error/fatal); `tenant_id`/`property_id` ASLA tag olarak set edilmez. Replit Secrets: `SENTRY_ENVIRONMENT=pilot`. Tam routing tablosu (11 alarm), severity matrix, manuel Sentry-UI kurulum: `docs/SENTRY_ALERT_POLICY.md`.
- **#5 Admin Sistem Sağlığı — Pilot Section**: `frontend/src/pages/SystemHealthDashboard.jsx`'a "Pilot Production Safety" section eklendi (Genel durum şeridi ↔ KPI satırı arası). Tek endpoint: `axios.get('/production-golive/readiness')` (Promise.allSettled 13. çağrı). 5 KpiCard: Readiness Verdict / CM Outbox / Circuit Breakers / Atlas Backup / Observability (`sentry_active` + `otel_active` root scalar field'lar — nested DEĞİL). Header'da 3 doc tooltip path. IIFE pattern + nullable-safe (state null ise section gizli, error state YOK). Mevcut UI sıfır kırılma.
- **#6 Kill-Switch / Feature Flag Standardı**: Helper `backend/infra/feature_flags.py` — `is_enabled` / `is_disabled` / `production_guard(flag, allowed_envs={dev,test,sandbox,ci,local})` / `snapshot()`. Tutarlı parser (`1/true/yes/on/y/t`); bilinmeyen token → WARNING + default. `production_guard` güvenlik bypass'ı prod'da YOKSAYILIR + WARNING. `snapshot()` privacy-safe (raw env value YOK); `requested != active` farkı leak'i fark ettirir. `KNOWN_FLAGS` tuple = mevcut 5 kill-switch (kod ↔ doc lock-step). Operatör doc'u: `docs/KILL_SWITCH_REGISTRY.md` — naming standardı, mevcut envanter, 6 önerilen yeni flag (DEFER). Bu tur **standart-belirleme** turu — mevcut 5 call site (`expo_push.py:60`, `auth_throttle.py:161`, `auth.py:134`, `quick_id_proxy.py:32`, `security_ops_router.py:126`) migrate EDİLMEDİ; ileri turlarda PR per call site.
- **#7 Pilot İlk 24h İzleme Runbook**: `docs/PILOT_FIRST_24H_MONITORING.md` — operatör nöbet defteri. Tasarım: zaman bantlarına göre azalan frekans (T+0→T+15dk her 5dk; T+15dk→T+1h her 15dk; T+1h→T+6h her 30dk; T+6h→T+24h her 2sa). Bölümler: yoğun bakım + akut faz + stabilizasyon + sürekli izleme + eşik tabloları (ROLLBACK derhal: 5xx>50%, login %0, folio loss, Mongo pool exhausted, PII leak / Sadece izle: tek CB OPEN, outbox 50-100, P95 2-3sn) + operasyon defteri şablonu + tatbikat modu + T+24h sonrası transition.
- **#8 Replit OPS Cheat-Sheet**: `docs/REPLIT_OPS_CHEATSHEET.md` — pilot 24/7 nöbet için tek-sayfa operatör referansı. Tasarım: "30 saniyede cevap" — §0 acil durum kısayolu (`bash deploy/rollback.sh`), §1 health endpoint matrisi, §3 sorun→triage akışı (9 belirti + 5dk karar matrisi), §4 yaygın senaryolar, §5 eskalasyon, §6 alfabetik komut listesi, §8 Replit-spesifik notlar (workflow restart, secrets vault GUI ASLA terminal, `/tmp/logs/<workflow>_*.log`). §7 çapraz-link 9 runbook.

## Pointers

- **FastAPI Documentation**: [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)
- **React Documentation**: [React Docs](https://react.dev/learn)
- **MongoDB Documentation**: [MongoDB Manual](https://www.mongodb.com/docs/manual/)
- **Redis Documentation**: [Redis Docs](https://redis.io/docs/)
- **Celery Documentation**: [Celery User Guide](https://docs.celeryq.dev/en/stable/userguide/index.html)
- **Tailwind CSS**: [Tailwind CSS Docs](https://tailwindcss.com/docs)
- **shadcn/ui**: [shadcn/ui Docs](https://ui.shadcn.com/)
- **TanStack Query**: [TanStack Query Docs](https://tanstack.com/query/latest)
- **React Router**: [React Router Docs](https://reactrouter.com/en/main)
- **i18next**: [i18next Docs](https://www.i18next.com/overview/getting-started)
- **Vitest**: [Vitest Docs](https://vitest.dev/guide/)
- **pytest**: [pytest Docs](https://docs.pytest.org/en/stable/)
- **PCI DSS v4.0**: [PCI DSS Resources](https://www.pcisecuritystandards.org/document_library/)
- **RFC 6238 (TOTP)**: [RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238)
- **HTNG 2024B XML**: For Sabre SynXis integration.
- **OData V4 JSON**: For SAP S/4HANA integration.
