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

### Phase 1 — Auth + Credential Security
- SecretManager / credential vault
- KMS encryption integration
- Token rotation support

### Phase 2 — Mock + Read/Write Path E2E
- Mock HotelRunner server (port 9999)
- Ingest pipeline (webhook/pull -> validate -> dedup -> map -> persist -> trace)
- ARI outbound (outbox pattern)
- 27/27 tests passed

### CSP Fix for /api/redoc
- Nginx + FastAPI middleware CSP headers fixed
- Production deployment verified

### Phase 3 — HotelRunner v2 Connector (Production-Grade) [2026-03-30]
New connector: `backend/channel_manager/connectors/hotelrunner_v2/`

**Architecture:**
- `endpoint_map.py` — v1/v2 mixed path mapping (per HR docs)
- `client.py` — Async HTTP client (httpx, typed responses, error taxonomy)
- `mapper.py` — Bi-directional mapper matching REAL HR API format
- `errors.py` — Error taxonomy (auth, validation, rate_limit, timeout, server, parse)
- `retry.py` — Exponential backoff (max 5, jitter) + Dead Letter Queue
- `service.py` — Business logic orchestration + transaction verification
- `feature_flags.py` — Tenant-based flags (enabled, shadow_mode, write_enabled)
- `metrics.py` — Operational metrics (success rate, latency, error taxonomy)
- `reconciliation.py` — PMS vs HR comparison, drift detection, auto-fix
- `router.py` — REST API (17 endpoints under /api/channel/hotelrunner-v2/)

### Phase 4 — P0 Live Production Test [2026-03-30]
- Successfully tested all endpoints against real HotelRunner production API
- Auth, rooms, reservations, channels verified
- Shadow mode stable, DLQ empty, no errors

### Phase 5 — P1 Ops Dashboard Frontend [2026-03-30]
New page: `/hrv2-ops` → `frontend/src/pages/HRv2OpsDashboard.jsx`

**Panels:**
1. **Provider Health Panel** — Auth status, Reservations API, Shadow Mode, Write Path, Son Pull, Latency, DLQ, Retry count
2. **Operational Actions** — Baglanti Testi, Reconciliation Baslat, Provider Durumu Yenile, Feature Flags display
3. **Sync Overview** — Drift count, success rate, total operations, last reconciliation
4. **Failure Visibility** — Error taxonomy, DLQ entries, or "Hata yok" empty state
5. **Recent Events** — Last 10 connector events with operation, correlation_id, duration, timestamp
6. **Recent Drifts** — Drift entries with case_type, severity, or empty state
7. **Operations Breakdown** — Table: operation, total, success, failed, success%, avg/max latency

**Backend:** New aggregated endpoint `GET /api/channel/hotelrunner-v2/ops-dashboard` 
**Tenant Fix:** set_tenant_context override for JWT/query param tenant_id mismatch
**Testing:** 13/13 backend tests passed, frontend UI 100% verified (iteration 163)

## API Endpoints (v2 Connector)

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/channel/hotelrunner-v2/status | Connector health + metrics |
| GET | /api/channel/hotelrunner-v2/ops-dashboard | Aggregated ops dashboard data |
| GET | /api/channel/hotelrunner-v2/trace/{id} | Reservation timeline trace |
| POST | /api/channel/hotelrunner-v2/test-connection | Connection smoke test |
| POST | /api/channel/hotelrunner-v2/pull-reservations | Pull reservations |
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

### P1 — Write Path Transition Plan
- Shadow -> Dry-run -> Limited Live -> Full Live transition
- Controlled write path enablement

### P2 — PII Phase 3: Strict Mode Enforcement
### P2 — Wire failure tracking
### P2 — App.jsx Decomposition
### P3 — Legacy HR connector migration/cleanup
