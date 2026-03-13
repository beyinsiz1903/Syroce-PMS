# RoomOps PMS - Product Requirements Document

## Core Product
Hotel Property Management System (PMS) with Channel Manager integration for Turkish hospitality market.

## Architecture
- **Backend:** FastAPI + MongoDB (async)
- **Frontend:** React + Shadcn/UI + Tailwind CSS
- **Providers:** HotelRunner (REST/webhook), Exely (SOAP/pull) — 2-provider architecture

## Channel Manager Data Model (v2.0) — 9 Collections

| # | Collection | Purpose |
|---|---|---|
| 1 | `provider_connections` | Provider credentials & connection config |
| 2 | `room_mappings` | PMS room type -> provider room code |
| 3 | `rate_plan_mappings` | PMS rate plan -> provider rate code |
| 4 | `raw_channel_events` | Immutable event store (webhook/pull/replay) |
| 5 | `reservation_lineage` | Gold table: reservation tracking & reconciliation |
| 6 | `ari_change_sets` | ARI push pipeline state |
| 7 | `ari_outbound_logs` | Provider communication audit log |
| 8 | `ari_drift_state` | ARI parity / consistency tracking |
| 9 | `channel_reconciliation_cases` | Discrepancy tracking |

## Reservation Ingest Pipeline

```
HotelRunner webhook / Exely pull
        |
  raw_channel_events (persist)
        |
  Stage 2: Duplicate Detection (provider_event_id)
  Stage 3: Payload Hash Check
  Stage 4: Stale Event Detection
  Stage 5: Normalize (HR/Exely -> canonical)
  Stage 6: Mapping Resolution
  Stage 7: Decision Engine (create/update/cancel/skip/pending_mapping/manual_review)
  Stage 8: Lineage Update + Reconciliation Cases
```

### Workers
1. **HotelRunner Pull** (10min interval) — MOCKED stub
2. **Exely Pull** (5min interval) — MOCKED stub
3. **Ingest Processor** (10s interval) — processes pending raw events
4. **Replay Worker** (5min interval) — retries failed events

## Cross-Provider Reconciliation Engine (IMPLEMENTED — 2026-03-13)

### Architecture
```
Provider Snapshot Collection (HotelRunner REST / Exely SOAP)
        ↓
PMS Reservations (reservation_lineage)
        ↓
Comparison Engine (6 mismatch types)
        ↓
Case Creation + Auto-Resolution
        ↓
Dashboard + Operational APIs
```

### Mismatch Types
| Type | Severity | Auto-Resolve? |
|---|---|---|
| `missing_reservation` | high | YES — auto-import |
| `ghost_reservation` | medium | NO — manual review |
| `amount_mismatch` | medium | NO — manual review |
| `date_conflict` | high | NO — manual review |
| `status_conflict` | critical | NO — manual review |
| `duplicate_reservation` | medium | YES — auto-merge |

### Reconciliation API (`/api/channel-manager/reconciliation/`)
- `GET /cases` — List cases with filters (status, severity, case_type, provider)
- `GET /cases/{id}` — Case detail
- `POST /cases/{id}/resolve` — Resolve case
- `POST /cases/{id}/ignore` — Ignore case
- `POST /cases/{id}/acknowledge` — Acknowledge case (under review)
- `POST /run` — Trigger manual reconciliation
- `POST /run-with-snapshots` — Run with test provider snapshots
- `GET /dashboard` — Dashboard summary (severity, provider, type breakdowns)
- `GET /metrics` — Observability metrics
- `GET /worker/status` — Worker status

### Components
- **comparison_engine.py** — Core mismatch detection logic
- **snapshot_collectors.py** — Provider-specific snapshot fetchers (MOCKED)
- **reconciliation_worker.py** — Periodic worker + run_with_snapshots
- **auto_resolver.py** — Safe auto-resolution rules
- **reconciliation_router.py** — FastAPI endpoints

## Key API Endpoints

### Ingest Pipeline (`/api/channel-manager/ingest/`)
- `POST /inject-and-process` — Inject + immediate pipeline processing
- `POST /inject` — Inject only (async processing)
- `GET /status` — Pipeline status (events, lineage, recon, workers)
- `GET /events` — Raw channel event list
- `GET /events/stats` — Event processing statistics
- `POST /workers/process` — Trigger ingest processor
- `POST /workers/replay` — Trigger replay worker
- `POST /workers/pull/{provider}` — Trigger pull worker

### HotelRunner Webhooks
- `POST /api/channel-manager/hotelrunner/webhooks/reservations`
- `POST /api/channel-manager/hotelrunner/webhooks/modifications`
- `POST /api/channel-manager/hotelrunner/webhooks/cancellations`

### Data Model API (`/api/channel-manager/model/`)
- Full CRUD for connections, room/rate mappings, lineage, reconciliation cases

## Completed Features
- PMS Core (rooms, bookings, guests, folios, tasks)
- ARI Push Engine (event -> buffer -> coalesce -> push pipeline)
- 9-Collection Data Model with full CRUD API
- **Reservation Ingest Pipeline** (8-stage, production-grade) — P0 VERIFIED
- **Cross-Provider Reconciliation Engine** — P0 VERIFIED (2026-03-13)
  - 6 mismatch type detection
  - Auto-resolution for safe cases
  - Case lifecycle (open → acknowledged → resolved/ignored)
  - Dashboard with metrics, filters, provider breakdown
  - 22/22 backend tests + 100% frontend tests pass
- **Frontend DataModelDashboard** with 5 tabs:
  - Ingest Pipeline (workers, raw events, stats)
  - Lineage (reservation tracking)
  - Connections (provider config)
  - Mappings (room/rate plan mappings)
  - Reconciliation (engine controls, metrics, filters, cases with actions)

## Pending / Upcoming
- **P1:** Pull Workers — Real API Calls implementation (HotelRunner REST, Exely SOAP)
- **P1:** Real Provider Snapshot Collection for reconciliation engine
- **P2:** Legacy Collection Cleanup
- **P3:** Mapping UI Enhancement

## Removed from Backlog
- Channex & SiteMinder integrations (user confirmed not needed)

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |

## Test Reports
- `/app/test_reports/iteration_66.json` — P0 Ingest Pipeline Full Verification
- `/app/test_reports/iteration_67.json` — P0 Reconciliation Engine Full Verification (22/22 backend, 100% frontend)
