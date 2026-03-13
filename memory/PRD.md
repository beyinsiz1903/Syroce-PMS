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

## Completed Features (P0 VERIFIED - 2026-03-13)
- PMS Core (rooms, bookings, guests, folios, tasks)
- ARI Push Engine (event -> buffer -> coalesce -> push pipeline)
- 9-Collection Data Model with full CRUD API
- **Reservation Ingest Pipeline** (8-stage, production-grade)
  - HotelRunner webhook integration
  - Exely SOAP pull integration (stub)
  - Duplicate/stale/hash detection
  - Decision engine (6 outcomes)
  - Loop prevention (external_write_protected)
  - Reconciliation case auto-creation
  - Replay mechanism for failed events
- **Frontend DataModelDashboard** with 5 tabs:
  - Ingest Pipeline (workers, raw events, stats)
  - Lineage (reservation tracking)
  - Connections (provider config)
  - Mappings (room/rate plan mappings)
  - Reconciliation (discrepancy cases)

## Pending / Upcoming
- **P0:** Cross-Provider Reconciliation Engine (awaiting user spec)
- **P1:** HotelRunner Sandbox Real Test (real API credentials)
- **P1:** Pull Workers — Real API Calls implementation
- **P2:** Exely Live Connection Test (real SOAP credentials)
- **P3:** Mapping UI Enhancement
- **P3:** Legacy Collection Cleanup

## Removed from Backlog
- Channex & SiteMinder integrations (user confirmed not needed)

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |

## Test Reports
- `/app/test_reports/iteration_4.json` — Data Model refactor
- `/app/test_reports/iteration_5.json` — Ingest Architecture
- `/app/test_reports/iteration_66.json` — P0 Full Verification (37/37 backend, 5/5 frontend tabs)
