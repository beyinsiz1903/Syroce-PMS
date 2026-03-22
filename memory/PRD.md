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
- Covers: Dashboard/Control Plane, Incident Timeline, Key Rotation, Breach Simulation, Infrastructure Maturity, Architecture Consistency, PMS Battle Testing, Folio Hardening, Stress Testing, Real-World Exposure, Learning Loop
- Concrete data models, API contracts, workflows, failure modes, metrics for every section
- 30-day week-by-week execution roadmap with Go/No-Go criteria

## Pending Tasks (from Blueprint)

### P0 — Week 1: Foundations
- Wire FailureTracker into import_bridge_service, outbox_worker, ARI push
- Implement Event Timeline (collection + writer + API)
- Implement Feature Gate system (collection + API + kill switch)
- Implement Dashboard Aggregator + Snapshot Worker
- Run crypto migration (SEC-002)
- Enable STRICT_TENANT_MODE in staging

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
- Frontend control plane dashboard
- Grafana dashboards
- Full breach simulation suite
- Terraform modules for production

### P2 — Tech Debt
- Fix pre-existing test failures
- Fix pre-existing lint errors
- Legacy file cleanup (~80 files in backend/ root)
- ~264 legacy db imports → tenant-scoped access
