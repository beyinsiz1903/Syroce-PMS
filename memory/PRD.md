# Syroce PMS — Product Requirements Document

## System Overview
Hotel PMS + Channel Manager platform. FastAPI backend, MongoDB, Redis. Multi-tenant architecture with OTA/provider integrations (Exely, HotelRunner). Outbox pattern, import/ingest pipelines, idempotency protections. AES-256-GCM encryption with AAD binding.

## Core Architecture
- `/app/backend/` — FastAPI backend
- `/app/backend/controlplane/` — OPS-001 Control Plane module
- `/app/backend/core/` — Core services (outbox, import bridge, crypto, secrets)
- `/app/backend/channel_manager/` — Channel manager adapters
- `/app/backend/workers/` — Background workers (ARI push, retry, etc.)
- `/app/backend/tests/resilience/` — Chaos testing and resilience validation suite
- `/app/backend/docs/BATTLE_READINESS_BLUEPRINT.md` — Battle-grade execution blueprint

## Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Completed Features

### OPS-001: Production-Grade Control Plane
- Core module at `/app/backend/controlplane/`
- Failure taxonomy (5 types: RETRYABLE, PERMANENT, PROVIDER_ERROR, DATA_ERROR, SECURITY_ERROR)
- 15 API endpoints under `/api/ops/*`
- Idempotent retry engine with dry-run support
- Alerting engine with cooldowns and webhook support
- 14 operational runbooks
- Startup validator
- 38 unit tests + 29 API tests (all passing)

### CHAOS-001: Chaos Testing & Resilience Validation Program
- Comprehensive 10-part strategy document (`CHAOS_TESTING_MASTER_PLAN.md`)
- 69 resilience tests across 7 test files — all passing
- Test categories: Provider failures, Worker failures, Retry/Replay safety, Crypto resilience, Tenant isolation, Ops visibility, Burst/Soak
- Game day plan, automation strategy, pilot readiness checklist

### BATTLE-GRADE EXECUTION BLUEPRINT (2026-02-15)
- 10-section production evolution blueprint (`BATTLE_READINESS_BLUEPRINT.md`, 2576 lines)
- Covers all sections from Dashboard to Learning Loop
- Concrete data models, API contracts, workflows, failure modes, metrics
- 30-day week-by-week execution roadmap with Go/No-Go criteria

### CORE BATTLE LOOP (2026-03-22) — Week 1 MVP
Implementation of the "minimum battle loop" — the three systems that make the platform visible:

#### 1. Event Timeline System
- **Collection**: `event_timeline` with 5 indexes (entity, correlation, external_id, stage_health, TTL 90d)
- **TimelineWriter** (`controlplane/timeline_writer.py`): Fire-and-forget event appender, never blocks main flow
- **TimelineReader** (`controlplane/timeline_reader.py`): Read + gap detection + stuck event finder
- **Timeline API** (`controlplane/timeline_router.py`): 5 endpoints under `/api/ops/timeline/*`
  - `GET /api/ops/timeline/external/{external_id}` — Primary debug entry point (OTA reservation → full trace)
  - `GET /api/ops/timeline/correlation/{correlation_id}` — Full flow trace with entity map
  - `GET /api/ops/timeline/{entity_type}/{entity_id}` — Entity timeline with gap warnings
  - `GET /api/ops/timeline/search` — Search with filters
  - `GET /api/ops/timeline/gaps` — Stuck event detection
- **Performance**: Traces reservation in <1 second (goal was <5 seconds)

#### 2. FailureTracker Wiring
- **import_bridge_service.py**: On failure → records structured failure to `cp_failures` + timeline event
- **outbox_worker.py**: On permanent failure → records to `cp_failures` + timeline event
- **Timeline events**: Written at `import_decided`, `stored`, `queued`, `dispatched`, `confirmed` stages

#### 3. Minimal Dashboard (Read-Only)
- **DashboardAggregator** (`controlplane/dashboard_aggregator.py`): 8 parallel queries, health score algorithm
- **DashboardSnapshotWorker**: Stores time-series snapshots every 60s in `cp_health_snapshots`
- **Dashboard API** (`controlplane/dashboard_router.py`): 5 endpoints under `/api/ops/dashboard/*`
  - `GET /api/ops/dashboard` — Full system dashboard (score, grade, metrics, connectors, pipeline)
  - `GET /api/ops/dashboard/tenant/{id}` — Tenant-scoped dashboard
  - `GET /api/ops/dashboard/trends` — Historical health score trends
  - `GET /api/ops/dashboard/connectors` — Connector health
  - `GET /api/ops/dashboard/pipeline` — Pipeline depth
- **Health Score**: 0-100 weighted (critical failures 30%, high 20%, outbox 15%, import 15%, sync 10%, ARI 5%, security 5%)
- **Grades**: A (90-100), B (75-89), C (60-74), D (40-59), F (0-39)

## Pending Tasks (from Blueprint)

### P0 — Week 2: Hardening
- Implement immutable folio_ledger + reconciliation engine
- Implement key rotation (data model + API + ReEncryptionWorker)
- PMS battle tests (split reservation, no-show, room change, overbooking, cancellation)
- Implement Learning Loop (IncidentClassifier, recurrence detection, never-again rules)

### P0 — Week 3: Stress + Exposure
- Reservation Burst test (15K reservations)
- ARI Storm test (120K updates)
- Provider Downtime simulation
- Pilot hotel shadow mode + canary rollout

### P0 — Week 4: Production
- Ramp pilot to 100%
- Secrets management rollout (SEC-001)
- Multi-hotel onboarding
- 48-hour soak test
- Go/No-Go decision

### P1 — Important
- Frontend control plane dashboard UI
- Grafana dashboards
- Full breach simulation suite
- Terraform modules for production
- Execute Crypto Migration (SEC-002)
- Execute Secrets Management Rollout (SEC-001)

### P2 — Tech Debt
- Fix pre-existing test failures
- Fix pre-existing lint errors
- Legacy file cleanup (~80 files in backend/ root)
- ~264 legacy db imports → tenant-scoped access
