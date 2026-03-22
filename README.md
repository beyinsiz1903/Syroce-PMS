# Syroce PMS — Enterprise Hotel Property Management System

Multi-tenant Property Management System with integrated Channel Manager, Control Plane, and Governance Layer. Built for production hotel operations with OTA connectivity, real-time event tracing, and automated deployment pipelines.

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | React | 19 |
| Styling | Tailwind CSS + shadcn/ui | - |
| Backend | FastAPI (Python) | 3.11+ |
| Database | MongoDB | 7.0+ |
| Runtime | Node.js | 20+ |
| Linting | Ruff (backend), ESLint v9 (frontend) | - |
| CI/CD | GitHub Actions (hard-gate pipeline) | - |

## Core Modules

### Property Management (PMS)
- Front desk: check-in/out, walk-ins, room moves
- Reservation calendar with drag-and-drop
- Housekeeping task management
- Folio management with charges and payments
- Night audit with automated procedures
- Invoicing and financial reports

### Channel Manager
- OTA integrations: Exely (SOAP/XML), HotelRunner (REST/JSON)
- Two-way sync: reservations in, ARI (Availability/Rates/Inventory) out
- Ingest pipeline with deduplication, normalization, validation
- Outbox pattern for reliable ARI distribution
- Provider configuration and connection testing

### Control Plane (Operations)
- **Reservation Trace**: End-to-end webhook-to-booking timeline (<1s lookup)
- **System Health**: Real-time health grade (A-F) with metric cards
- **Live Feed**: Last 50 events with auto-refresh
- Event timeline with gap detection and stuck event finder
- Raw webhook payload viewer (SOAP XML / JSON)
- Failure tracking with structured taxonomy (5 types)
- 14 operational runbooks with idempotent retry engine

### Governance Panel (Admin)
- **Entitlement Enforcement**: Plan-based module access control (403 blocking)
- **Usage Metering**: 15 event types, daily/monthly aggregation, tenant leaderboard
- **Feature Flags**: Percentage rollout, kill switch, tenant overrides, expiry
- **Onboarding Automation**: 12-step checklist with auto-detection from DB
- **Deploy Pipeline**: 6 hard gates (lint, test, security, migration, build, smoke)

### Additional Modules
- Revenue management with dynamic pricing
- Guest loyalty program
- Group sales and CRM
- Multi-language support (8 languages: EN, TR, DE, AR, RU, IT, FR, ES)
- Role-based access control with JWT authentication
- AES-256-GCM encryption with AAD binding

## Architecture

```
/app
  backend/
    bootstrap/        # App wiring: routers, middleware, workers, DI
    controlplane/     # OPS: timeline, dashboard, failure tracker, alerting
    core/             # Entitlement, metering, feature flags, outbox, crypto
    channel_manager/  # OTA adapters (Exely, HotelRunner), domain model
    domains/          # Business domains: admin, PMS, guest, revenue, sales
    modules/          # Standalone modules: folio, reservations, analytics
    ops/              # Deploy pipeline, rollback engine, smoke tests
    routers/          # HTTP route handlers
    security/         # Tenant guard, rate limiter, credential guard
    workers/          # Background: ARI push, retry, queue monitor
    tests/            # Test suite (304 curated CI tests)
  frontend/
    src/
      components/     # Shared components + shadcn/ui primitives
      pages/          # Route-level pages
      hooks/          # Custom React hooks
      i18n/           # Translations (8 languages)
```

## Quick Start

### Demo Account
```
Email: demo@hotel.com
Password: demo123
```

### Local Development
```bash
# Backend
cd backend
pip install -r requirements.txt
# Requires: MONGO_URL, JWT_SECRET in .env

# Frontend
cd frontend
yarn install
yarn start
# Requires: REACT_APP_BACKEND_URL in .env
```

### Running Tests
```bash
# Backend lint
cd backend && ruff check .

# Backend tests (curated CI suite)
cd backend && pytest tests/test_hardening_comprehensive.py tests/test_controlplane_api.py ...

# Frontend lint
cd frontend && yarn lint
```

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci-cd.yml`) enforces strict hard gates — no `|| true` allowed:

| Gate | Tool | Scope |
|------|------|-------|
| Backend Lint | `ruff check .` | Full backend (excl. `_legacy/`) |
| Frontend Lint | `npx eslint src/ --quiet` | All frontend source |
| Backend Tests | `pytest` (curated suite) | 304 tests across 10 paths |
| Security Audit | `pip-audit` + `yarn audit` | Dependencies |
| Build | Dockerfile validation | Both services |

The in-app deploy pipeline (`/api/deploy/pipeline/run-all`) adds migration verification and smoke tests (8 HTTP endpoints).

## Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | User authentication |
| `/api/rooms` | GET | List rooms |
| `/api/bookings` | GET/POST | Reservations |
| `/api/guests` | GET | Guest profiles |
| `/api/ops/timeline/external/{id}` | GET | Reservation trace |
| `/api/ops/dashboard` | GET | System health |
| `/api/deploy/pipeline/run-all` | POST | Full deploy pipeline |
| `/api/admin/entitlements/overview` | GET | Tenant entitlements |
| `/api/admin/metering/overview` | GET | Usage metrics |

## Database

MongoDB collections organized by domain:

- **Core**: `users`, `tenants`, `rooms`, `guests`, `bookings`
- **Financial**: `folios`, `folio_charges`, `folio_payments`, `invoices`
- **Operations**: `housekeeping_tasks`, `night_audit_logs`
- **Channel Manager**: `provider_configs`, `outbox_queue`, `ingest_events`
- **Control Plane**: `event_timeline`, `cp_failures`, `cp_health_snapshots`, `webhook_raw_payloads`
- **Governance**: `usage_daily`, `feature_flags`, `onboarding_progress`
- **Deploy**: `deploy_pipelines`

## Environment Variables

```bash
# Backend (.env)
MONGO_URL=<mongodb-connection-string>
DB_NAME=<database-name>
JWT_SECRET=<min-32-char-random-string>

# Frontend (.env)
REACT_APP_BACKEND_URL=<backend-url>
```

## Documentation

- `backend/docs/BATTLE_READINESS_BLUEPRINT.md` — 10-section production blueprint
- `backend/docs/CHAOS_TESTING_MASTER_PLAN.md` — Resilience testing strategy
- `backend/docs/ONBOARDING_PLAYBOOK.md` — Pilot hotel onboarding process
- `backend/docs/CONTROLPLANE_ARCHITECTURE.md` — Control Plane design
- `backend/docs/ENCRYPTION_ARCHITECTURE.md` — Crypto and secrets design
- `memory/PRD.md` — Product requirements and task tracking
- `memory/CHANGELOG.md` — Detailed change history

## License

MIT

---

**Version**: 2.0.0 | **Last Updated**: 2026-03
