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
- **E2E pilot residue sweep (Task #178)** — `backend/scripts/cleanup_e2e_pilot_residue.py`: pilot tenant'ta 24+ saatten eski `E2E_` prefix'li `bookings`/`guests`/`folio_charges` kayıtlarını listeler (dry-run default), `--apply` ile bookings→cancelled + charges→voided=true (guests rapor edilir, silinmez). Guard'lar: `E2E_PILOT_TENANT_ID` zorunlu (yoksa rc=2), `--apply` için ayrıca `E2E_ALLOW_PILOT_CLEANUP=true` (rc=2 fail-closed). Sonuç `e2e_residue_scans` koleksiyonuna metric row yazılır (`found_total>0 → rc=1` dry-run'da, cron alerting için). Test: `backend/tests/test_cleanup_e2e_pilot_residue.py` (5 case: env guard, apply guard, tenant/prefix/age filter, no-op cancel guard).
- **F8R–F8W Hardening Pack (DONE 2026-05-23)** → `docs/adr/2026-05-f8r-f8w-hardening.md` — 5 yeni spec: F8U auth_token_lifecycle (`98-auth-token-lifecycle`), F8V ws_tenant_isolation (`98B-websocket-tenant-isolation`), F8R export_artifact_idor (`91-export-artifact-idor`), F8S file_upload_security (`64-file-upload-security`), F8W ops_readiness (`09-ops-readiness-smoke`). Doctrine: paylaşılan stress bearer'a dokunma (F8U fresh login), module-block tekil scope, P0=tenant/auth bypass, P1=contract/threshold, P2=info; final invariant her spec'te zorunlu.
- **F8 Stress Test Series** — F8A/B/C/D/E/I/L/M faz detayları, tur tarihçesi, module-blocked doctrine, helper konvansiyonları → `docs/GOTCHAS.md` "F8 Stress Test Series" bölümü. Roadmap (tek doğruluk kaynağı): `docs/STRESS_TEST_ROADMAP.md`. **✅ GREEN BASELINE (2026-05-23, commit `a035568c`)**: Full Operational Stress Suite tek run → 413 test, 0 fail, 662 PASS / 0 FAIL adım, P0=P1=0, external_calls=[], pilot_drift=0, cleanup idempotent, süre 2758.8s. F8D-v3 HR coverage extension (33B/35B/38/38B/39/39B) full-suite içinde geçti. Detay: `docs/drill_reports/20260523_stress_full_stress_suite_GREEN.md`. Fix kuyruğu: 33B JSON export `callTimed` headers eksik → raw `request.get` (commit `8cee3050`); starlette 1.0.0 PYSEC-2026-161 → `starlette>=1.0.1` pin (commit `a035568c`). Mutlak kurallar her fazda: pilot mutation=0, external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH.

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
