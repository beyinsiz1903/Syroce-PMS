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

**Architecture:**
- `endpoint_map.py` — v1/v2 mixed path mapping (per HR docs, NOT single version)
- `client.py` — Async HTTP client (httpx, typed responses, error taxonomy)
- `mapper.py` — Bi-directional mapper matching REAL HR API format (rooms.inv_code, daily_prices, payments, etc.)
- `errors.py` — Error taxonomy (auth, validation, rate_limit, timeout, server, parse)
- `retry.py` — Exponential backoff (max 5, jitter) + Dead Letter Queue
- `service.py` — Business logic orchestration + transaction verification
- `feature_flags.py` — Tenant-based flags (enabled, shadow_mode, write_enabled)
- `metrics.py` — Operational metrics (success rate, latency, error taxonomy)
- `reconciliation.py` — PMS vs HR comparison, drift detection, auto-fix
- `router.py` — REST API (16 endpoints under /api/channel/hotelrunner-v2/)

**HotelRunner API Endpoints Used:**
- `GET /api/v1/apps/infos/channels` — Channel list
- `GET /api/v1/apps/infos/transaction_details` — ARI push verification
- `GET /api/v2/apps/rooms` — Room/rate inventory
- `PUT /api/v2/apps/rooms/~` — ARI update (by inv_code, NOT rate_code)
- `GET /api/v2/apps/reservations` — Reservation pull (pagination, filters)
- `PUT /api/v2/apps/reservations/~` — Reservation delivery confirmation

**Production Credentials:**
- Token: eTMI2v1DvFz8fSXYVX5xC_j3eda7gKw_32SOFm_a (stored encrypted in SecretManager)
- HR ID: 373816343 (stored encrypted in SecretManager)
- Base URL: https://app.hotelrunner.com

**Test Results:** 33/33 tests pass (21 unit + 12 integration), 15/15 API endpoints 200 OK

## API Endpoints (v2 Connector)

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/channel/hotelrunner-v2/status | Connector health + metrics |
| GET | /api/channel/hotelrunner-v2/trace/{id} | Reservation timeline trace |
| POST | /api/channel/hotelrunner-v2/test-connection | Connection smoke test |
| POST | /api/channel/hotelrunner-v2/pull-reservations | Pull reservations (full HR params) |
| POST | /api/channel/hotelrunner-v2/ingest | Ingest single reservation |
| POST | /api/channel/hotelrunner-v2/push-ari | ARI push (with verification) |
| POST | /api/channel/hotelrunner-v2/confirm-delivery | Confirm delivery to HR |
| GET | /api/channel/hotelrunner-v2/verify-transaction/{id} | Verify ARI transaction |
| POST | /api/channel/hotelrunner-v2/reconcile | Trigger reconciliation |
| GET | /api/channel/hotelrunner-v2/reconciliation/history | Past reconciliation runs |
| GET | /api/channel/hotelrunner-v2/reconciliation/drifts | Recent drift entries |
| GET | /api/channel/hotelrunner-v2/flags | Get feature flags |
| PUT | /api/channel/hotelrunner-v2/flags | Update feature flags |
| GET | /api/channel/hotelrunner-v2/metrics | Metrics summary |
| GET | /api/channel/hotelrunner-v2/dlq | Dead letter queue |
| POST | /api/channel/hotelrunner-v2/dlq/{id}/retry | Retry DLQ entry |

## Upcoming Tasks

### P0 — Live Production Test
- Run test-connection against real HR API (production credentials stored)
- Pull real reservations from production
- Validate mapper with live data

### P1 — Ops Dashboard Frontend
- Provider health panel (HR + Exely side by side)
- Sync status, error rates, last operations

### P1 — Write Path DRY-RUN → Live Transition
- Controlled shadow → dry-run → live transition
- ARI push verification via transaction_details

### P2 — PII Phase 3: Strict Mode Enforcement
### P2 — App.jsx Decomposition
### P3 — Legacy migration/cleanup
