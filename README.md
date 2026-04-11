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
    domains/          # Business domains:
      admin/          #   Subscriptions, entitlements, control panel
      ai/             #   AI service, dynamic pricing, predictions, reputation
      channel_manager/#   CM domain logic, mappings, ARI
      guest/          #   Check-in, messaging, WhatsApp, journey
      hr/             #   Staff & HR management
      pms/            #   Front desk, rooms, housekeeping, night audit, folio
      revenue/        #   RMS, pricing, analytics, forecasting
      sales/          #   CRM, group sales
    infra/            # Infrastructure: cache, headers, metrics, DB optimizer
    modules/          # Standalone modules: folio, reservations, analytics, ML
    ops/              # Deploy pipeline, rollback engine, smoke tests
    routers/          # HTTP route handlers
    security/         # Tenant guard, rate limiter, credential guard
    workers/          # Background: ARI push, retry, queue monitor
    tests/            # Test suite (391+ curated CI tests)
    _legacy/          # Deprecated modules (excluded from lint/CI)
  frontend/
    src/
      components/     # Shared components + shadcn/ui primitives
      pages/          # Route-level pages (164 modules, lazy-loaded)
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
# Requires: VITE_BACKEND_URL in .env
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
| Backend Tests | `pytest` (curated suite) | 391+ tests across 14 paths |
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
VITE_BACKEND_URL=<backend-url>
```

## Security Status (Current Snapshot)

| Layer | Tool | Status | Detail |
|-------|------|--------|--------|
| Backend (Python) | `pip-audit` | **0 unignored** | 2 known-accepted: ecdsa timing (out-of-scope), nltk WordNet (unused) |
| Frontend (Node) | `yarn audit --level high` | **0 High / 0 Critical** | Clean Vite 8 dependency tree |
| Secrets | `grep` + Trivy | **Clean** | No hardcoded secrets, CRITICAL filesystem scan passes |
| CI Gate | GitHub Actions | **Hard gate** | pip-audit + yarn audit high + Trivy CRITICAL = merge blocker |

> Full vulnerability reduction history: `memory/CHANGELOG.md` (87 -> 29 -> 14 -> 0)

## Test Health

| Tier | Location | Count | CI Gate | Description |
|------|----------|-------|---------|-------------|
| **T0** Battle | `tests/battle/` | 46 | Hard gate | Booking invariants, regression guards, hold/OOO, folio, learning loop |
| **T1** Curated | `ci-cd.yml` list | 345+ | Hard gate | Core integration + unit tests across 14 paths |
| **T2** Quarantine | `tests/_quarantine/` | ~37 | Excluded | Controlled tech debt (ADR-002) — reviewed monthly |

**CI result: 391+ tests, 0 failures.**

Quarantine breakdown (37 tests, not running in CI):
- `stale_fixtures`: 10 (rate_manager — needs room_type seed data)
- `changed_api`: 10 (endpoint behavior/schema changed post-refactor)
- `changed_implementation`: 13 (checkout flow, timeline, crypto v2 not yet enabled)
- `external_dependency`: 3 (require live HotelRunner API)
- `meta-test`: 1 (references restored file, needs update)

> 70+ tests restored from quarantine on 2026-03-23. See `backend/docs/ADR_TEST_QUARANTINE_STRATEGY.md`.

## Documentation

- `backend/docs/BATTLE_READINESS_BLUEPRINT.md` — 10-section production blueprint
- `backend/docs/CHAOS_TESTING_MASTER_PLAN.md` — Resilience testing strategy
- `backend/docs/ONBOARDING_PLAYBOOK.md` — Pilot hotel onboarding process
- `backend/docs/CONTROLPLANE_ARCHITECTURE.md` — Control Plane design
- `backend/docs/ENCRYPTION_ARCHITECTURE.md` — Crypto and secrets design
- `backend/docs/CHANNEL_CAPABILITY_MATRIX.md` — Exely/HotelRunner provider parity matrix
- `backend/docs/PILOT_KPI_FRAMEWORK.md` — Pilot hotel KPI measurement criteria
- `backend/docs/ADR_TEST_QUARANTINE_STRATEGY.md` — Test quarantine triage (ADR-002)
- `backend/docs/ADR_ROOM_TYPE_INVENTORY_STRATEGY.md` — Inventory model (ADR-003)
- `memory/PRD.md` — Product requirements and task tracking
- `memory/CHANGELOG.md` — Detailed change history

## License

MIT

---

**Version**: 2.1.1 | **Last Updated**: 2026-02
