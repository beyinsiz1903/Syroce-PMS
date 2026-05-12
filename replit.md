# Syroce PMS

An enterprise-grade, multi-tenant Hotel Property Management System with AI-powered features adaptable to any accommodation type.

## Run & Operate

- **Frontend**:
  - Install dependencies: `cd frontend && yarn install`
  - Start dev server: `cd frontend && yarn run start`
  - Build for deployment: `cd frontend && yarn build`
- **Backend**:
  - Start services (MongoDB, Redis, FastAPI): `bash backend/start.sh`
- **Environment Variables**: `JWT_SECRET`, `RESEND_API_KEY`, `SENTRY_DSN`, `VITE_SENTRY_DSN`, `QUICKID_SERVICE_KEY`, `QUICKID_URL`, `ENABLE_QUICKID_DEMO`, `ROOM_QR_SECRET`, `PUBLIC_APP_URL`, `AFSADAKAT_BASE_URL`, `AFSADAKAT_ADMIN_TOKEN`, `ENABLE_SETUP_ENDPOINTS`, `SETUP_SECRET`, `EXELY_IP_WHITELIST`, `EXELY_TRUST_FORWARDED`, `EXELY_TRUSTED_PROXY_IPS`, `JWT_EXPIRATION_MINUTES`, `REFRESH_TOKEN_EXPIRATION_DAYS`, `DISABLE_EXPO_PUSH`, `MOBILE_PUSH_SCAN_SECONDS`, `MOBILE_PUSH_VIP_WINDOW_MINUTES`, `KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`.

## Stack

- **Frontend**: React 19, Vite 8, Tailwind CSS, shadcn/ui, TanStack Query v5, React Router v7, i18next, Yarn 1.22.22, Vitest.
- **Backend**: FastAPI (Python 3.11+), MongoDB 7.0+ (motor), Redis, Celery, pytest.
- **Auth**: JWT, AES-256-GCM, RBAC.

## Where things live

- `frontend/`: React + Vite application.
- `backend/`: FastAPI Python application (contains `bootstrap/`, `channel_manager/`, `controlplane/`, `core/`, `domains/`, `modules/`, `workers/`).
- `infra/`: Prometheus/Grafana/K8s config.
- `deploy/`: Deployment scripts.
- `docs/`: ADRs and playbooks.
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

- **API Call Conventions**: Use relative paths WITHOUT `/api/` for `axios` calls; use `/api/` explicitly for native `fetch`.
- **MongoDB Atlas 500-Collection Limit**: Workarounds like embedded arrays or discriminator fields are used.
- **JWT Lifespan**: Backend default `JWT_EXPIRATION_MINUTES=15` overridden to `10080` (7 days) in Replit Secrets. Frontend attempts silent refresh on 401. Revocation is active.
- **CORS Configuration**: Ensure `CORS_ORIGINS` is correctly set in `.replit`.
- **Image Uploads**: Strict validation for type, size, and dimensions.
- **Exely Webhook**: Requires `EXELY_IP_WHITELIST` in production, otherwise 503 error. **Format**: comma-separated literal IPv4/IPv6 addresses (NOT CIDR — webhook does literal string match at `exely_webhook_router.py:394`). CIDR is only valid for `EXELY_TRUSTED_PROXY_IPS` (XFF proxy resolution). **Verification (Pilot Readiness hard-blocker #1, May 2026)**: run `python backend/scripts/verify_exely_whitelist.py --env production --expect-ips "$PILOT_EXELY_IPS"` before deploy — verdict model PASS/REVIEW/FAIL, IPs redacted in output (`1.2.3.4` → `1.2.x.4`). Same `verify()` function is wired into `infra/readiness_validator.py` (alt-check `exely_whitelist`, counts only, no raw IPs in JSON) and `server.py` startup guardrail (CRITICAL log on production blockers, no abort — readiness/deploy smoke is the gate). 46 tests cover redaction + verdict + readiness wiring (`tests/test_verify_exely_whitelist.py` + `tests/test_readiness_validator_exely_check.py`).
- **Production Secret Management**: Critical secrets like `JWT_SECRET` must be set via Replit Secrets vault in production; hardcoded values may block startup.
- **Night Audit N+1 Issues**: Optimized with `asyncio.gather` and bulk operations; avoid sequential DB calls in loops.
- **Outbound HTTP Calls**: Tenant-configurable outbound URLs are protected with DNS-rebinding-safe transport, IP allowlisting, and transport pinning.
- **Auth Cache Invalidation**: Handled via Redis pub/sub in multi-worker environments.
- **CapX Integration**: Integration with A-plan via encrypted tenant credentials and event-driven updates.
- **Walk-in Placeholder Guest Names**: API responses replace placeholder names (e.g., "C4", "X") with `Walk-in Misafir #XXXX` while preserving original DB values.
- **Color Palette Convention**: Migrate from `purple-*` to `indigo-*` and `orange-*` to `amber-*` for Tailwind classes. Do not use `purple` or `orange` for new code.
- **In-App Dialog System**: Use `frontend/src/lib/dialogs.js` Promise API (`confirmDialog/alertDialog/promptDialog`) instead of native `window.alert/confirm/prompt`.
- **Sprint A Design System (May 2026)**: Use `<PageHeader icon title subtitle actions>` from `frontend/src/components/ui/page-header.jsx` for all page tops (icon kutu + h1 + subtitle + sağda actions slot). Use `<KpiCard icon label value sub intent highlight active onClick>` from `frontend/src/components/ui/kpi-card.jsx` for KPI grids — `intent` palette: `info` (sky), `success` (emerald), `warning` (amber), `danger` (rose), `neutral` (slate), `default`. Interactive (onClick'li) KpiCard otomatik `role=button + tabIndex=0 + Enter/Space + focus-visible` ekler. Use `<StatusBadge intent icon>` from `frontend/src/components/ui/status-badge.jsx` for status pills (aynı intent paleti). Standartlar: Yenile butonu HER YERDE `<Button variant="outline" size="sm"><RefreshCw className="w-4 h-4 mr-1.5"/>Yenile</Button>`; primary CTA = default Button (siyah dolu) — gradient/blue/green özel renk YOK. **İSTİSNA**: ReservationCalendar "Rezervasyon ekle" butonu **bilinçli** amber kaldı (en sık kullanılan marka aksiyonu). Pilot uygulanan sayfalar (12): DepartureList, NoShowToday, WakeUpCallsPage, LostFoundPage, DepositTracking, ArrivalList, HousekeepingDashboard, MaintenanceWorkOrders, NightAuditDashboard, FrontdeskAuditChecklist, RMSModule, MailingPage (Mayıs 2026 — KPI grid: violet/red gradient → KpiCard intent info/success/info/warning/danger; PageHeader BarChart3 ikonu; Yenile butonu `?refresh=1` ile cache_manager `_nocache` kwarg'ını tetikler). PMSModule Quick Actions sade beyaz Card'a çevrildi (mavi gradient kaldırıldı). Procurement PR action'ları ghost link → outline + ikon (Send/Check/X/Ban). Para birimi: BookingDetailDialog $ hardcode'u `formatCurrency(amount, currency || 'TRY')` ile değiştirildi (`frontend/src/lib/currency.js`). Tarih lokali: takvim gün kısaltmaları `Pts/Car` → `Pzt/Çar` düzeltildi (`pages/calendar/calendarHelpers.jsx`); CalendarHeader date range `month: 'short'` → `'long'` (May → Mayıs). Emoji yok kuralı 4 yerde uygulandı (ReservationCalendar/OnlineCheckin/PredictiveAnalytics/AIRMSDashboard). Boş durum CTA'ları LostFoundPage ve SuppliesMarket'e eklendi. AIRMSDashboard EN→TR + gradient kaldırıldı.
- **Pages Layout Wrap (Current Default — M5, May 2026)**: Routes own the Layout sarımı, NOT pages. Add `wrapLayout: true, layoutModule: "..."` to the route entry in `frontend/src/routes/routeDefinitions.jsx`; the page returns just its content (no `import Layout`, no `<Layout>` JSX). **Önemli**: `layoutModule` değeri NAV_ITEMS'daki gerçek `key` ile eşleşmeli (örn. `walkin`, `eod_report`, `room_map`, `shift_handover`) — boş veya yanlış key ("dashboard" gibi placeholder) bırakılırsa standalone "Kontrol Paneli" butonu sürekli aktif görünür ve üst menüde aynı anda iki sekme mavi çıkar (Mayıs 2026 fix). 118/123 pages migrated via `tools/codemod-layout/codemod.mjs` (brace-aware AST-lite codemod, dry-run + diff + apply modes). 11 pages intentionally retain in-page `<Layout>`: 6 use `MaybeLayout` (conditional embed for hub-rendered pages — out of scope), 4 are imported but never routed (PMSModule/RMSModule/Reports/GuestJourneyDashboard — render only as hub children), 1 (`ReservationCalendar.jsx`) returns two distinct `currentModule` values conditionally (`reservation_calendar` vs `calendar`) and must keep its in-component branching. **Regression guard**: `cd frontend && yarn guard:layout` (or `node tools/codemod-layout/guard.mjs`) fails if any route with `wrapLayout: true` points to a page that still imports `Layout` — prevents double-wrap.
- **WS Redis Pub/Sub Circuit Breaker**: Prevents log/CPU spam by enforcing a cool-down period if the Redis listener fast-exits repeatedly.
- **CM-Hardening Series (May 2026)**: Overbooking alert emission (Turu #1a) + Conflict Queue API (#1b) + UI (#1c) + Bulk Resolve (#2) + No-Show OTA Outbox Parity #3a (event production) + #3b (HotelRunner inventory recompute, Strategy A). Tam detay, test pinleri, dosya/satır referansları, out-of-scope ve architect follow-up'lar → `docs/adr/2026-05-cm-hardening.md`. Önemli kısa not: HotelRunner provider'da transactional booking metodu YOK (cancel bile inventory recompute kullanır); no-show parity de aynı yoldan gider. `outbox_dispatcher.EVENT_TYPE_TO_CM_EVENT["booking.no_show.v1"] = "booking_no_show"`.
- **Production Hardening Series (May 2026)**: No-Show Terminal-State Guard (`NON_NOSHOWABLE_STATES`, ikinci no-show 400 + audit_count==1) + No-Show Inventory Lock Release (`handle_no_show` → `release_booking_nights`, INV-6 simetrisi) + Closed Folio Refund/Void Guard (`FolioHardeningService.post_refund/void_charge/void_payment` `folio.status != "open"` iken 4xx). Tam detay, test pinleri, hata mesajları, operasyonel notlar → `docs/adr/2026-05-production-hardening.md`.
- **Exely No-Show Parity GAP (CM-Hardening Turu #3c — DISCOVERY COMPLETE, DEFERRED, May 2026)**: Pilotta Exely müşterisi yok → uygulama defer; discovery turu kod yazmadan tam mimari haritayı çıkardı. Kök sebep: repo'da **iki paralel CM modülü** var ve farklı `ConnectorProvider` enum'ları kullanıyorlar — `backend/channel_manager/domain/models/connector_account.py:18` (`HOTELRUNNER, SITEMINDER, CHANNEX` — **EXELY yok**, EventSyncService bu enum'u kullanır) vs `backend/domains/channel_manager/data_model.py:29` (`HOTELRUNNER, EXELY` — provider push tarafı). EventSyncService akışı (Turu #3a + #3b): outbox_dispatcher → `EventSyncService.handle_event("booking_no_show", ...)` → `repo.get_active_connectors(tenant_id, property_id)` (`channel_manager/infrastructure/repository.py:48-51` — `connector_accounts` koleksiyonu). Exely conn'lar **ayrı `exely_connections` koleksiyonunda** olduğu için boş liste döner → `outbox_dispatcher.py:75-77` "No active connectors → mark as processed" diye **sessizce yutar**. Sonuç: Exely-only tenant'lar için no-show DAHİL `booking_created/cancelled/modified` gerçek-zamanlı push almıyor — periyodik `exely_pull_worker.py` (180s) + `availability_reconciliation_worker.py` (15min) gap'i kapsıyor, pilot süresince katlanılabilir. `ExelyProvider.push_ari` rate+avail birleşik tek metot — `_dispatch_single_event` HR pattern'ine (`push_availability`/`push_rates` ayrı) doğrudan map etmiyor, adapter gerekecek. **İki strateji**: Strategy A (~4-6 saat, ÖNERİLEN) — `EventSyncService.handle_event` içinde `exely_connections` köprüsü + yeni `_dispatch_exely_event` helper, `_dispatch_single_event` ve enum'a dokunmadan; Strategy B (~1-2 gün, Q3 2026) — full unification, `ConnectorProvider.EXELY` ekleme + `_dispatch_single_event` Exely kolu + schema migration. Tam discovery raporu (akış haritası, dosya/satır pinleri, fiili davranış) → `docs/adr/2026-05-cm-hardening.md` (Turu #3c bölümü ~70 satır).
- **Stop-Sale Circuit Breaker (CM-Hardening Turu #4, May 2026)**: Persistent provider outage'larında log/CPU spam'i durdurmak için `provider_failover.CircuitBreaker` artık HR `push_daily_inventory`+`push_date_range_inventory` ve Exely `push_ari` etrafında sarıldı. Per-connection key (`hotelrunner:{conn_id}` / `exely:{conn_id}`) → tenant izolasyonu. Breaker OPEN iken HTTP/SOAP YAPILMAZ; `ProviderResult(success=False, error_type="CircuitOpen", metadata.circuit_open=True)` döner. Defaults: `failure_threshold=5`, `recovery_timeout=60s`, `half_open_max_calls=3`. Retry policy altında → transient flutter'lar trip etmez. UI: `GET /api/channel-manager/unified-rate-manager/circuit-breakers` (severity OPEN>HALF_OPEN>CLOSED, RBAC `view_system_diagnostics`); UnifiedRateManager header altı pill banner sadece kötü durumda görünür; 30s interval; bulk update toast `channel_push_count>0 && breaker open` ise warning. Tam detay + 7 test pini → `docs/adr/2026-05-cm-hardening.md` (Turu #4). Out-of-scope: `_push_to_*` bg task'ları fire-and-forget olduğu için sync `succeeded[]/failed[]` mümkün değil; HR `update_room`/`push_ari_bulk` ileriki tur.
- **Atlas-Managed Backup (Production Safety #2, May 2026)**: Pilot DB MongoDB Atlas M10+ üzerinde → continuous backup + PITR + S3 snapshot Atlas managed (yerel mongodump'a gerek YOK). `backend/infra/atlas_backup_check.py` URI'den `.mongodb.net` host suffix'ini algılar; `ATLAS_TIER` env-var'ı ile plan seviyesi (M10/M20/M30…) okunur. `backend/infra/readiness_validator.py:97-112` backup check Atlas-aware: Atlas + M10+ → `status="atlas_managed", score=1.0` (BACKUP_ENABLED=false bile olsa). Atlas + M0 + production → `score=0.0` (FAIL). Non-Atlas legacy path korundu (BackupManager.get_status). Opsiyonel doğrulama: `python backend/scripts/verify_atlas_backup.py --max-age-hours 26` (Atlas Admin API key'leri varsa snapshot tazeliği kontrol eder, yoksa no-op). Restore senaryoları + tier matrisi: `docs/ATLAS_BACKUP_AND_RESTORE.md`. Replit Secrets'a eklenmesi gereken: `ATLAS_TIER=M10` (zorunlu); `ATLAS_API_PUBLIC_KEY`/`ATLAS_API_PRIVATE_KEY`/`ATLAS_PROJECT_ID`/`ATLAS_CLUSTER_NAME` (opsiyonel — sadece snapshot tazelik doğrulaması için).
- **Tek Komutlu Rollback (Production Safety #1, May 2026)**: `deploy/rollback.sh` — `last_good_tag`'den önceki başarılı imaj tag'ine döner + `deploy/smoke.sh` otomatik koşar; PASS → `last_good_tag` günceller, FAIL → `.rollback_from` sidecar bırakır manuel inceleme için. Args: `[tag]` (override), `--list` (mevcut tag'leri göster), `--dry-run` (komut çalıştırmaz). `deploy/deploy.sh:170-174` başarılı deploy sonunda `IMAGE_TAG`'i (yoksa `git rev-parse --short HEAD`, o da yoksa timestamp) `deploy/.last_good_tag`'e yazar. **STALE referans düzeltmesi:** Eski `bash deploy/deploy.sh --rollback` referansları (`docs/PILOT_GO_NO_GO.md:343,502` + `docs/PILOT_GO_NO_GO_HR_TEMPLATE.md:308`) gerçekte hiçbir zaman desteklenmemişti — `deploy/rollback.sh`'a yönlendirildi. Tam rehber: `docs/ROLLBACK.md` (4 senaryo: kod hatası, auto-rollback, Atlas restore, tam felaket).
- **HotelRunner Pull Retries**: `sync_scheduler.pull_for_tenant` initializes `HotelRunnerProvider(max_retries=…)` per call. Manual sync uses 3, scheduled cycles use 2 (was 0 — caused unhandled transient 504s to surface as ERROR logs even though the next cycle would compensate). With `base_delay=2.0`, `jitter=0.5`, 2 retries add ~3–9s (avg ~6s) — well within the 3-min cycle. Keep ≥1 to absorb single-shot HotelRunner gateway 504/timeouts.

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