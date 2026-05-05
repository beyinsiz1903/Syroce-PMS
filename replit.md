# Syroce PMS

An enterprise-grade, multi-tenant Hotel Property Management System with AI-powered features adaptable to any accommodation type.

## Run & Operate

- **Frontend**:
  - Install dependencies: `cd frontend && yarn install`
  - Start dev server: `cd frontend && yarn run start`
  - Build for deployment: `cd frontend && yarn build` (outputs to `frontend/build`)
- **Backend**:
  - Start services (MongoDB, Redis, FastAPI): `bash backend/start.sh`
- **Environment Variables**:
  - `JWT_SECRET`: Persistent environment variable for authentication.
  - `RESEND_API_KEY`: For email services. Set `RESEND_FROM` for custom domains.
  - `SENTRY_DSN` (backend), `VITE_SENTRY_DSN` (frontend): For error tracking.
  - `QUICKID_SERVICE_KEY`, `QUICKID_URL`: Quick-ID microservice integration.
  - `ENABLE_QUICKID_DEMO`: `true` for fake Quick-ID data in development.
  - `ROOM_QR_SECRET`: HMAC secret for QR token generation.
  - `PUBLIC_APP_URL`: Base URL for QR links.
  - `AFSADAKAT_BASE_URL`, `AFSADAKAT_ADMIN_TOKEN`: For Af-sadakat integration.
  - `ENABLE_SETUP_ENDPOINTS`: Enables setup endpoints (default `0`).
  - `SETUP_SECRET`: Secret for setup endpoints.
  - `EXELY_IP_WHITELIST`: Mandatory for Exely webhook, list of trusted IPs.
  - `EXELY_TRUST_FORWARDED`: `1` to trust `X-Forwarded-For` header for Exely webhooks.
  - `EXELY_TRUSTED_PROXY_IPS`: CIDR list of trusted proxies for Exely webhooks.
  - `JWT_EXPIRATION_MINUTES`: Access token expiry (default 15 min).
  - `REFRESH_TOKEN_EXPIRATION_DAYS`: Refresh token expiry (default 30 days).
  - `DISABLE_EXPO_PUSH`: `1` to disable Expo Push.
  - `MOBILE_PUSH_SCAN_SECONDS`: Push notification scan interval.
  - `MOBILE_PUSH_VIP_WINDOW_MINUTES`: VIP arrival push window.
  - `KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`: Interval for ID photo view alerts.

## Stack

- **Frontend**: React 19, Vite 8, Tailwind CSS, shadcn/ui, TanStack Query v5, React Router v7, i18next (10 languages), Yarn 1.22.22, Vitest.
- **Backend**: FastAPI (Python 3.11+), MongoDB 7.0+ (motor), Redis, Celery, pytest.
- **Auth**: JWT, AES-256-GCM, RBAC.

## Where things live

- `frontend/`: React + Vite application.
- `backend/`: FastAPI Python application.
  - `bootstrap/`: App wiring and DI.
  - `channel_manager/`: OTA adapters.
  - `controlplane/`: Operational monitoring.
  - `core/`: Entitlements, metering, crypto.
  - `domains/`: DDD modules (pms, guest, revenue, ai, hr).
  - `modules/`: Business logic (folio, inventory, reservations).
  - `workers/`: Background tasks.
- `infra/`: Prometheus/Grafana/K8s config.
- `deploy/`: Deployment scripts.
- `docs/`: ADRs and playbooks.
- **Key Files**:
  - DB Schema: Managed by MongoDB collections; see `backend/models/schemas/` for Pydantic models.
  - API Contracts: Defined by FastAPI routers (`backend/routers/`, `backend/domains/*/router.py`).
  - Theme Files: `frontend/tailwind.config.js`.

## Architecture decisions

- **Multi-tenant Architecture**: Each hotel operates on an isolated data set within the same system instance, enforced by `tenant_id` scoping on all database operations and API calls.
- **Property Type Profiling System**: Dynamically configures PMS modules, navigation, and features based on the chosen property type (e.g., pension, boutique, resort).
- **Atomic Operations**: Critical workflows like multi-room booking, check-in/out, and resource locking (Spa/MICE) use MongoDB transactions or unique compound indexes to ensure atomicity and prevent race conditions.
- **Security-First Development**: Extensive adversarial testing has led to robust defenses against IDOR, XSS, SSRF, mass assignment, JWT manipulation, deserialization, and various injection attacks.
- **Event-Driven Integrations**: Syroce Xchange (SXI) bus for reliable, idempotent distribution of hotel events to partner systems (Sabre SynXis, SAP S/4HANA, generic webhooks) with SSRF protection.
- **Fail-Closed Principle**: Security-critical configurations (e.g., `JWT_SECRET`, webhook secrets) default to fail-closed, refusing to boot or operate insecurely if not explicitly configured for production.

## Product

- **Core PMS**: Front desk, reservations, housekeeping, financial folios, guest management.
- **AI Integration**: AI-powered upsell offers, dynamic pricing, forecasting, no-show risk scoring, guest pattern analysis.
- **Channel Management**: Unified Rate Manager, OTA sync with Exely and HotelRunner, SXI bus for external systems.
- **Financial Operations**: Cashier module, PCI-DSS compliance dashboard, automated Turkish Accommodation Tax declarations, Procurement (PR/PO/GRN).
- **Guest Experience**: Room QR requests, guest reviews & NPS, digital key, mobile staff/guest apps.
- **Operational Efficiency**: Spa & MICE/Banquet management, shift handover, in-app help center, regulatory reports (TÜİK, Ministry inspection readiness).
- **Security & Compliance**: 2FA/TOTP, KVKK/GDPR, comprehensive audit logging, Quick-ID integration for identity verification.

## User preferences

_Populate as you build_

## Gotchas

- **API Call Conventions**: Use relative paths WITHOUT `/api/` for `axios` calls (Vite proxy handles it). Use `/api/` explicitly for native `fetch` calls. Mixing these will lead to double prefixes or missing prefixes.
- **MongoDB Atlas 500-Collection Limit**: Workarounds like embedded arrays (`price_tiers`/`promotions` in `supplies_market_products`) or discriminator fields (`_kind` for `kbs_reports`) are used to avoid creating new collections.
- **JWT Lifespan**: Access tokens last 7 days (168 hours) by default; users remain logged in unless explicitly logged out or token expires. Revocation is implemented.
- **CORS Configuration**: Ensure `CORS_ORIGINS` is correctly set in `.replit` to prevent subdomain bypass.
- **Image Uploads**: Strict validation is in place for image files (type, size, dimensions). Attempts to upload non-image files or oversized images will result in 400/413 errors.
- **Exely Webhook**: Requires `EXELY_IP_WHITELIST` to be explicitly set in production; otherwise, it will return a 503 error.
- **Production Secret Management**: `JWT_SECRET` and other critical secrets must be set via Replit Secrets vault in production environments; hardcoded values in `.replit` will block startup if `STRICT_JWT_SECRET=1` or `ENV=production`.
- **Night Audit N+1 Issues**: Performance-sensitive areas in night audit have been optimized with `asyncio.gather` and bulk operations. Avoid sequential DB calls in loops.
- **Outbound HTTP Calls**: All tenant-configurable outbound URLs are protected with DNS-rebinding-safe transport, IP allowlisting, and transport pinning to prevent SSRF.
- **Auth Cache Invalidation**: In multi-worker environments, user and tenant document cache invalidation is handled via Redis pub/sub to ensure consistency across instances.
- **CapX Integration (UAT GREEN, May 2026)**: A-plan ile uçtan uca canlı. Tenant credential paketi (`base_url`, `api_key`, `webhook_secret`) `capx_tenant_credentials` koleksiyonunda AES-256-GCM şifreli; `PUT /api/capx/tenant-credentials/{tenant_id}` ile yazılır. Adapter şeması: availability `{date_start, date_end, rooms:[{room_type, available_count, price_min, price_max, currency, pax}], auto_publish, pms_external_ref}`; reservation event `event_type` regex `^reservation\.(created|updated|cancelled)$` + zorunlu `external_id`. Callback URL formatı `{PUBLIC_BASE_URL}/api/webhooks/capx/by-tenant/{tenant_id}` (HMAC iki yönlü). Scheduler env yoksa SADECE tenant credential olan tenant'ları gezer (`backend/integrations/capx/scheduler.py:_push_cycle`).
- **WS Redis Pub/Sub Circuit Breaker**: `backend/infra/ws_redis_adapter.py` listener `<1s` içinde 5 kez ardarda fast-exit ederse WARNING log'ları susturup 30s zorunlu cool-down uygular; 5 dk sonra otomatik reset. Gerçek arızayı maskelemez, sadece tight-loop log/CPU spam'ini engeller. Tunable: `_breaker_threshold/_breaker_cooldown_s/_breaker_window_s`.

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