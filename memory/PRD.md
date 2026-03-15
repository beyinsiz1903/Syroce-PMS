# RoomOps PMS — Product Requirements Document

## Original Problem Statement
Build a production-grade **Cross-Provider Reconciliation Engine** and **Operational Channel Monitoring & Alerting System** for a PMS + Channel Manager integration platform. The platform integrates with HotelRunner (REST) and Exely (SOAP) as external channel managers.

---

## Core Architecture
- **Backend:** FastAPI (Python) on port 8001
- **Frontend:** React on port 3000
- **Database:** MongoDB (9+ collections for channel manager)
- **Providers:** HotelRunner (REST), Exely (SOAP)

## Key Subsystems
1. **Reservation Ingest Pipeline** — Pull & webhook-based event ingestion
2. **ARI Push Engine** — Outbound availability/rate/inventory sync
3. **Cross-Provider Reconciliation Engine** — Mismatch detection & case management
4. **Operational Monitoring & Alerting System** — Real-time health monitoring & alerting
5. **9-Collection Data Model** — Unified data schema

---

## Completed Features

### Cross-Provider Reconciliation Engine (Completed)
- Snapshot collectors for HotelRunner & Exely (real API calls)
- Comparison engine detecting 6 mismatch types
- Case management (create, resolve, ignore)
- Auto-resolution for safe cases
- Reconciliation dashboard with metrics
- **Test:** 22/22 backend tests pass (iteration_1)

### Operational Monitoring & Alerting System (Completed — March 2026)
- **5 Health Domains:** Provider, Ingest Pipeline, ARI Push, Reconciliation, Queue & Worker
- **Monitoring Worker:** 60s interval, auto-collects metrics & evaluates thresholds
- **Alert Engine:** 14 threshold types, auto-create/auto-resolve alerts
- **6 API Endpoints:**
  - `GET /api/channel-manager/monitoring/overview`
  - `GET /api/channel-manager/monitoring/alerts`
  - `GET /api/channel-manager/monitoring/metrics`
  - `GET /api/channel-manager/monitoring/providers`
  - `POST /api/channel-manager/monitoring/alerts/{id}/ack`
  - `POST /api/channel-manager/monitoring/alerts/{id}/resolve`
- **Frontend Dashboard:** Monitoring tab with health overview, domain cards, alert list, detailed metrics
- **Test:** 31/31 backend tests pass (iteration_68)

### Real Provider API Integrations (Completed — March 2026)
- Snapshot collectors upgraded from mocked stubs to real HotelRunnerProvider + ExelyClient
- Ingest pull workers use real provider API clients with pagination
- Graceful error handling when credentials not configured

---

## Database Collections
1. `provider_connections` — Provider credentials & status
2. `raw_channel_events` — Ingest pipeline events
3. `reservation_lineage` — Reservation tracking
4. `ari_change_sets` — ARI change queue
5. `ari_outbound_logs` — ARI push audit
6. `ari_drift_state` — ARI parity tracking
7. `channel_reconciliation_cases` — Reconciliation cases
8. `monitoring_alerts` — Monitoring alerts (NEW)

---

## Pending / Backlog Tasks

### P1
- Replace actual provider API credentials (HotelRunner token/hr_id, Exely username/password/hotel_code) for production use

### P2
- Legacy collection cleanup (archive/delete old unused collections)
- Mapping UI improvement (PMS room/rate mapping interface)
- Slack webhook integration for alert dispatch
- Email notification for alert dispatch

### P3
- Historical metrics storage for trend analysis
- Alert notification preferences per user
- Custom threshold configuration UI
