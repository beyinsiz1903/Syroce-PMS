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
- **Exely Webhook**: Requires `EXELY_IP_WHITELIST` in production, otherwise 503 error.
- **Production Secret Management**: Critical secrets like `JWT_SECRET` must be set via Replit Secrets vault in production; hardcoded values may block startup.
- **Night Audit N+1 Issues**: Optimized with `asyncio.gather` and bulk operations; avoid sequential DB calls in loops.
- **Outbound HTTP Calls**: Tenant-configurable outbound URLs are protected with DNS-rebinding-safe transport, IP allowlisting, and transport pinning.
- **Auth Cache Invalidation**: Handled via Redis pub/sub in multi-worker environments.
- **CapX Integration**: Integration with A-plan via encrypted tenant credentials and event-driven updates.
- **Walk-in Placeholder Guest Names**: API responses replace placeholder names (e.g., "C4", "X") with `Walk-in Misafir #XXXX` while preserving original DB values.
- **Color Palette Convention**: Migrate from `purple-*` to `indigo-*` and `orange-*` to `amber-*` for Tailwind classes. Do not use `purple` or `orange` for new code.
- **In-App Dialog System**: Use `frontend/src/lib/dialogs.js` Promise API (`confirmDialog/alertDialog/promptDialog`) instead of native `window.alert/confirm/prompt`.
- **Sprint A Design System (May 2026)**: Use `<PageHeader icon title subtitle actions>` from `frontend/src/components/ui/page-header.jsx` for all page tops (icon kutu + h1 + subtitle + sağda actions slot). Use `<KpiCard icon label value sub intent highlight active onClick>` from `frontend/src/components/ui/kpi-card.jsx` for KPI grids — `intent` palette: `info` (sky), `success` (emerald), `warning` (amber), `danger` (rose), `neutral` (slate), `default`. Interactive (onClick'li) KpiCard otomatik `role=button + tabIndex=0 + Enter/Space + focus-visible` ekler. Use `<StatusBadge intent icon>` from `frontend/src/components/ui/status-badge.jsx` for status pills (aynı intent paleti). Standartlar: Yenile butonu HER YERDE `<Button variant="outline" size="sm"><RefreshCw className="w-4 h-4 mr-1.5"/>Yenile</Button>`; primary CTA = default Button (siyah dolu) — gradient/blue/green özel renk YOK. **İSTİSNA**: ReservationCalendar "Rezervasyon ekle" butonu **bilinçli** amber kaldı (en sık kullanılan marka aksiyonu). Pilot uygulanan sayfalar (10): DepartureList, NoShowToday, WakeUpCallsPage, LostFoundPage, DepositTracking, ArrivalList, HousekeepingDashboard, MaintenanceWorkOrders, NightAuditDashboard, FrontdeskAuditChecklist. PMSModule Quick Actions sade beyaz Card'a çevrildi (mavi gradient kaldırıldı). Procurement PR action'ları ghost link → outline + ikon (Send/Check/X/Ban). Para birimi: BookingDetailDialog $ hardcode'u `formatCurrency(amount, currency || 'TRY')` ile değiştirildi (`frontend/src/lib/currency.js`). Tarih lokali: takvim gün kısaltmaları `Pts/Car` → `Pzt/Çar` düzeltildi (`pages/calendar/calendarHelpers.jsx`); CalendarHeader date range `month: 'short'` → `'long'` (May → Mayıs). Emoji yok kuralı 4 yerde uygulandı (ReservationCalendar/OnlineCheckin/PredictiveAnalytics/AIRMSDashboard). Boş durum CTA'ları LostFoundPage ve SuppliesMarket'e eklendi. AIRMSDashboard EN→TR + gradient kaldırıldı.
- **Pages Layout Wrap (Current Default — M5, May 2026)**: Routes own the Layout sarımı, NOT pages. Add `wrapLayout: true, layoutModule: "..."` to the route entry in `frontend/src/routes/routeDefinitions.jsx`; the page returns just its content (no `import Layout`, no `<Layout>` JSX). **Önemli**: `layoutModule` değeri NAV_ITEMS'daki gerçek `key` ile eşleşmeli (örn. `walkin`, `eod_report`, `room_map`, `shift_handover`) — boş veya yanlış key ("dashboard" gibi placeholder) bırakılırsa standalone "Kontrol Paneli" butonu sürekli aktif görünür ve üst menüde aynı anda iki sekme mavi çıkar (Mayıs 2026 fix). 118/123 pages migrated via `tools/codemod-layout/codemod.mjs` (brace-aware AST-lite codemod, dry-run + diff + apply modes). 11 pages intentionally retain in-page `<Layout>`: 6 use `MaybeLayout` (conditional embed for hub-rendered pages — out of scope), 4 are imported but never routed (PMSModule/RMSModule/Reports/GuestJourneyDashboard — render only as hub children), 1 (`ReservationCalendar.jsx`) returns two distinct `currentModule` values conditionally (`reservation_calendar` vs `calendar`) and must keep its in-component branching. **Regression guard**: `cd frontend && yarn guard:layout` (or `node tools/codemod-layout/guard.mjs`) fails if any route with `wrapLayout: true` points to a page that still imports `Layout` — prevents double-wrap.
- **WS Redis Pub/Sub Circuit Breaker**: Prevents log/CPU spam by enforcing a cool-down period if the Redis listener fast-exits repeatedly.
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