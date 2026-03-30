# Syroce PMS — Product Requirements Document

## Overview
Multi-tenant SaaS PMS + Channel Manager + Control Plane.
Canonical data model: Reservation, Inventory, Rate, Restriction.
Architecture: Outbox pattern, reconciliation, idempotent ingest, observability.

## Core Architecture
- **Backend**: FastAPI + MongoDB + Redis + Celery
- **Frontend**: React + Vite
- **Deployment**: Docker Compose (nginx, backend, worker, beat, mongo, redis)
- **Security**: KMS encryption, secret classification, rotation lifecycle, PII protection

## Completed Features

### Phase 1 — Auth + Credential Security ✅
- SecretManager / credential vault
- KMS encryption integration
- Token rotation support

### Phase 2 — Mock + Read/Write Path E2E ✅
- Mock HotelRunner server (port 9999)
- Ingest pipeline (webhook/pull → validate → dedup → map → persist → trace)
- ARI outbound (outbox pattern)
- 27/27 tests passed

### CSP Fix for /api/redoc ✅
- Nginx + FastAPI middleware CSP headers fixed
- Production deployment verified

### Phase 3 — HotelRunner v2 Connector (Production-Grade) ✅ [2026-03-30]
New connector: `backend/channel_manager/connectors/hotelrunner_v2/`

**Files created:**
- `__init__.py` — Module entry point
- `client.py` — Async HTTP client (httpx, typed responses, error taxonomy)
- `mapper.py` — Bi-directional mapper (HR ↔ canonical model)
- `errors.py` — Error taxonomy (auth, validation, rate_limit, timeout, server, parse)
- `retry.py` — Exponential backoff (max 5, jitter) + Dead Letter Queue
- `service.py` — Business logic orchestration (connection, pull, ingest, ARI push)
- `feature_flags.py` — Tenant-based flags (enabled, shadow_mode, write_enabled)
- `metrics.py` — Operational metrics (success rate, latency, error taxonomy)
- `reconciliation.py` — Daily reconciliation (PMS vs HR, drift detection, auto-fix)
- `router.py` — REST API (13 endpoints under /api/channel/hotelrunner-v2/)

**Requirements fulfilled:**
1. ✅ Connector Layer (adapter pattern, no legacy code)
2. ✅ Authentication (SecretManager, no plaintext, token rotation)
3. ✅ Reservation Ingest (new/modify/cancel, idempotency, dedup, raw payload storage, correlation_id)
4. ✅ ARI Sync Push (availability, rate, restriction, outbox, retry, verify)
5. ✅ Reconciliation (daily job, PMS vs HR comparison, drift detection, auto-fix)
6. ✅ Observability (timeline trace, connector health, last sync, failure taxonomy)
7. ✅ Error Handling (timeout, 4xx, 5xx, auth failure, retry policy, DLQ)
8. ✅ Security (KMS encrypted tokens, PII not logged, payload sanitized, audit trail)
9. ✅ Testing (18 unit tests + 11 integration tests = 29 total, all passing)
10. ✅ Feature Flags (tenant-based enable/disable)
11. ✅ Shadow Mode (ingest + compare only, no writes)
12. ✅ Metrics (sync success rate, ingest/push latency, drift rate, retry count, error taxonomy)

**API Endpoints (all 200 OK):**
- GET  /api/channel/hotelrunner-v2/status
- GET  /api/channel/hotelrunner-v2/trace/{reservation_id}
- POST /api/channel/hotelrunner-v2/test-connection
- POST /api/channel/hotelrunner-v2/pull-reservations
- POST /api/channel/hotelrunner-v2/ingest
- POST /api/channel/hotelrunner-v2/push-ari
- POST /api/channel/hotelrunner-v2/reconcile
- GET  /api/channel/hotelrunner-v2/reconciliation/history
- GET  /api/channel/hotelrunner-v2/reconciliation/drifts
- GET  /api/channel/hotelrunner-v2/flags
- PUT  /api/channel/hotelrunner-v2/flags
- GET  /api/channel/hotelrunner-v2/metrics
- GET  /api/channel/hotelrunner-v2/dlq

## Upcoming Tasks (Priority Order)

### P0 — Production HotelRunner Integration
- Replace mock server with real HotelRunner API (requires Base URL from user)
- Store production credentials via SecretManager
- Validate against real reservation data

### P1 — Ops Dashboard Frontend
- Provider health panel (HR + Exely side by side)
- Sync status, error rates, last operations
- Reconciliation run viewer

### P1 — HotelRunner Phase 4: Write Path DRY-RUN Exit
- Controlled transition: shadow → dry-run → live
- ARI push verification step
- Rollback capability

### P2 — PII Phase 3: Strict Mode Enforcement
### P2 — App.jsx Decomposition
### P3 — Legacy migration/cleanup
### P3 — Motor → pymongo async migration

## Credentials
- HR Token: `eTMI2v1DvFz8fSXYVX5xC_j3eda7gKw_32SOFm_a`
- HR ID: `373816343`
- Mock test credentials stored in SecretManager for tenant `test-tenant`
