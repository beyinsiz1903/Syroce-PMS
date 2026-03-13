# RoomOps PMS - Product Requirements Document

## Core Product
Hotel Property Management System (PMS) with Channel Manager integration for Turkish hospitality market.

## Architecture
- **Backend:** FastAPI + MongoDB (async)
- **Frontend:** React + Shadcn/UI + Tailwind CSS
- **Providers:** HotelRunner (REST), Exely (SOAP) — 2-provider architecture

## Channel Manager Data Model (v2.0) — 9 Collections
Optimized for 2-provider (HotelRunner + Exely) architecture. No over-abstraction.

| # | Collection | Purpose |
|---|---|---|
| 1 | `provider_connections` | Provider credentials & connection config |
| 2 | `room_mappings` | PMS room type → provider room code |
| 3 | `rate_plan_mappings` | PMS rate plan → provider rate code |
| 4 | `raw_channel_events` | Immutable event store (webhook/pull/replay) |
| 5 | `reservation_lineage` | Gold table: reservation tracking & reconciliation |
| 6 | `ari_change_sets` | ARI push pipeline state |
| 7 | `ari_outbound_logs` | Provider communication audit log |
| 8 | `ari_drift_state` | ARI parity / consistency tracking |
| 9 | `channel_reconciliation_cases` | Discrepancy tracking |

### Provider Enum
```
ConnectorProvider = hotelrunner | exely
```

## Key API Endpoints

### Data Model API (`/api/channel-manager/model/`)
- `GET /schema` — 9-collection schema overview
- `POST|GET|PUT|DELETE /connections` — Provider connection CRUD
- `POST /connections/{id}/activate|pause` — Connection lifecycle
- `POST|GET|DELETE /room-mappings` — Room mapping CRUD
- `POST|GET|DELETE /rate-plan-mappings` — Rate plan mapping CRUD
- `GET /raw-events` — Raw channel event listing
- `GET /lineage` — Reservation lineage listing
- `GET /lineage/stats` — Lineage statistics
- `POST|GET /reconciliation/cases` — Reconciliation case CRUD
- `POST /reconciliation/cases/{id}/resolve|dismiss` — Case resolution
- `GET /reconciliation/summary` — Summary statistics

### ARI Push Engine (`/api/channel-manager/ari/`)
- `POST /events` — Ingest ARI events
- `POST /push` — Trigger outbound push
- `GET /stats` — Pipeline statistics
- `GET|POST /drift/mode` — Dual-mode drift worker
- `GET /operational-metrics` — Provider health metrics

## Completed Features
- PMS Core (rooms, bookings, guests, folios, tasks)
- ARI Push Engine (event → buffer → coalesce → push pipeline)
- Enriched Delta Hash for outbound idempotency
- Dual-Mode Drift Worker (Normal/Recovery)
- Provider Test Harness scaffolding
- Dashboard Metrics (provider health, latency, queue stats)
- **9-Collection Data Model (v2.0)** with full CRUD API and frontend dashboard

## Pending / Upcoming
- **P1:** HotelRunner + Exely Reservation Ingest Architecture
- **P1:** HotelRunner Sandbox Real Test
- **P2:** Exely Live Connection Test
- **P3:** Mapping UI Enhancement
- **P4:** Reconciliation Engine & Dashboard
- **P5:** Channex Provider Integration (future)

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
