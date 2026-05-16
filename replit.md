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

Detaylı gotcha kayıtları, dosya/satır referansları ve tarihçe → **`docs/GOTCHAS.md`**. Aşağıda her bölümün tek-satırlık özeti:

- **Testing** — `frontend/e2e-business/` (20 spec, business-flow, pilot'a koşar, dış servisler SKIP) + `frontend/e2e-smoke/` (24 route × 2 viewport = 48 navigate test). Komutlar: `yarn test:e2e:business`, `yarn test:e2e:smoke`. Env zorunlu: `E2E_BASE_URL`/`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`.
- **Conventions (always-on)** — axios `/api/` YOK, fetch `/api/` VAR · `purple→indigo`/`orange→amber` · `lib/dialogs.js` (native alert/confirm değil) · walk-in misafir adı placeholder rewrite · image upload strict validation · outbound HTTP DNS-rebind safe + IP allowlist.
- **Auth, security & infra** — JWT 7gün override · Redis pub/sub auth invalidation + WS CB · Mongo Atlas 500-koleksiyon limiti workaround · Night Audit N+1 fix · HotelRunner pull retries (manual=3, scheduled=2) · Exely webhook IP allowlist literal (CIDR DEĞİL) + `verify_exely_whitelist.py`.
- **Design system & layout** — Sprint A: `<PageHeader>`/`<KpiCard intent>`/`<StatusBadge>`, Yenile=outline+RefreshCw, primary CTA siyah, emoji yok (ReservationCalendar amber bilinçli istisna) · M5 Layout wrap: routes own `wrapLayout+layoutModule`, page YOK; `yarn guard:layout` regression guard.
- **CM-Hardening Series (DONE)** → `docs/adr/2026-05-cm-hardening.md` — Conflict Queue + Bulk Resolve, No-Show OTA Outbox Parity, Stop-Sale Circuit Breaker (per-connection); Exely no-show parity #3c DEFERRED.
- **Production Hardening Series (DONE)** → `docs/adr/2026-05-production-hardening.md` — No-show terminal-state guard, no-show inventory lock release, closed-folio refund/void guard.
- **Production Safety Pack (8/8 DONE)** → `docs/PRODUCTION_SAFETY_PLAN.md`, operatör entry: `docs/REPLIT_OPS_CHEATSHEET.md`, prova: `docs/PRODUCTION_LAUNCH_REHEARSAL.md`. Paketler: rollback · Atlas-managed backup · CM observability single-source · Sentry alert+PII scrub · Admin pilot section · feature-flag std · 24h monitoring runbook · OPS cheat-sheet.
- **F8A Stress (DONE — #161 + tur-6 RESOLVED 2026-05-15)** — `frontend/e2e-stress/` 4 spec × Setup+A..F+ek-coverage = ~30 test (day-turnover/room-move/folio-mass/housekeeping-mass) 500-oda stress tenant'ta; defans: 5 gate, `external_calls_made:[]` (post-batch re-assert hook'u dahil), cleanup#1+idempotent#2, pilot drift=0. **Tur-6 fix (run #17 NO-GO → GO)**: (a) `/admin/stress/external-calls` endpoint top-level try/except + `logger.exception` ile sarmalandı (`backend/domains/admin/router/stress.py:417`); (b) seed sonrası `redis_cache.clear_pattern("rooms:{stress_tid}:*")` + `cache_warmer.cache.pop(...)` ile stress tenant rooms cache invalidasyonu (`stress.py:370`). **Tur-7 fix (run #19 NO-GO → GO hedefi)**: (a) `/admin/stress/external-calls` outbox loop'larına "inert delivery" filter eklendi (`stress.py:494,529`) — `delivery_message`/`last_error` "no active connectors|dry_run|unsupported event_type" içeren PROCESSED event'ler external call sayılmaz, çünkü stress tenant'ında CM connector yok, worker boş çalışıyor (false-positive #27 root cause); (b) 03-room-move setup `/api/pms/rooms` fetch'ine `?include_virtual=true` query param eklendi (`03-room-move.spec.js:66`) — endpoint'in `use_cache=False` branch'i zorlanır, cache_warmer'ın stale projection (stress_prefix eksik) snapshot'ı bypass edilir, fresh DB query stress_prefix dahil 500 room döner → eligible=0 fix; (c) 04-folio-mass split-by-amount throttle 120ms→1500ms (`04-folio-mass.spec.js:138`) — split write 1+N folio + 2N+1 charge yarattığı için "heavy" sınıf, sliding window rate limiter (apm_middleware) burst'ünde s429 atıyordu, 1.5s gap garantili boşaltır (toplam +15s test süresi). **Tur-6 round 2 fix (run #18 NO-GO → GO hedefi)**: (i) endpoint outbox sorgularına "dispatched-only" filter eklendi (`stress.py:461,484`) — `status="pending" + attempts=0` queue satırları normal davranıştır, "external call MADE" değildir; sadece `attempts>0` veya non-pending status sayılır; (ii) seed her 8. booking'i (i%8==0 → ~62) pre-vacant olarak yaratır (`room.status="available"`, `booking.status="checked_out"`, `room.current_booking_id=None`) → 03-room-move setup'ı zaten yeterli eligible görür, hiç force-checkout yapmaz, 108s timeout'tan kurtulur; (iii) seed folio'lara `total=balance=balance_total=total_amount=sum(charges)` yazıldı (`stress.py:265`) — 04-folio-mass C2 reconciliation testi artık `folio.total` = sum charges görür, mismatch sıfır. Helper PASS koşuluna `query_errors.length===0` eklendi (`frontend/e2e-stress/fixtures/stress-helpers.js:131`) — DB sorgusu fail olursa false-PASS önlenir. Tur-3 hardening: hard-fail `expect().not.toBe('FAIL')`, reporter `P1>0 → NO-GO`, `02 walk-in 50`, `03 positive-move 50 + post-move state transfer (RNL)`, `04 total reconciliation`, `08 OOO booking guard`. Acceptance contract `P0=P1=0`. **#161 fix (commit `5587e010`)**: stress seed `bookings_docs[].folio_id = fid` ekledi (`backend/domains/admin/router/stress.py:233`); spec'in `/api/pms/folios → /api/pms/bookings` fallback'i artık gerçek folio_id'yi yakalıyor → `04-folio-mass A/B/C` batch'leri 100/50/10 hedef folio'ya isabet ediyor. Repository projection `{"_id":0}` korunuyor (`modules/reservations/repository.py:36`), serializer alan dropluyor değil. Sonraki F8A workflow run'ı GO/GO WITH WATCH dönmeli. Replit 110s sandbox → chunked `-g <pattern>` runs. Detay: `docs/GOTCHAS.md` "F8A Stress Suite", rapor: `docs/drill_reports/20260514_stress_f8a_frontoffice_folio_hk.md` (eski NO-GO snapshot).

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
