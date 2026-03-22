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
- 25+ detailed test scripts (TS-001 through TS-025)
- Chaos injection fixtures (mock providers, crypto helpers, DB helpers)
- Factory fixtures for tenants, bookings, outbox events, import records, failures
- pytest markers for CI/CD cadence (chaos_l1 through chaos_l4)
- Game day plan, automation strategy, pilot readiness checklist

## Pending Tasks
- P0: Integrate Control Plane with Core Services (make it "live")
- P0: Execute Crypto Migration (SEC-002)
- P0: Execute Secrets Management Rollout (SEC-001)
- P1: Enable Strict Tenant Mode
- P2: Fix pre-existing test failures and lint errors
- P2: Frontend dashboards for Control Plane
