# RoomOps PMS - Product Requirements Document

## Original Problem Statement
Full-stack Hotel Property Management System (PMS) SaaS platform with multi-provider Channel Manager integration. Development phase declared complete. Current phase: operational validation, real-world integration testing, and multi-provider expansion.

## Current Phase: Multi-Provider Channel Manager

### Architecture
```
OTA (Booking.com / Expedia / Agoda)
    |
    v
Channel Manager Providers:
  ├── HotelRunner (REST API) ─── [Webhook + Scheduled Pull]
  └── Exely (SOAP/OTA)     ─── [Scheduled Pull via OTA_ReadRQ]
    |
    v
[Raw Event Store] ─── Audit + Replay
    |
    v
[Common Ingest Pipeline] ─── Provider-agnostic
    ├── Idempotency Guard ─── Dedup by external_id
    ├── Schema Normalizer ─── Provider format → Canonical PMS format
    ├── Room Mapping Check
    └── Decision Engine ─── create / update / cancel / skip / pending_mapping
    |
    v
[PMS ReservationService]
```

### What's Been Implemented

#### CI/CD Pipeline Fix (March 2026)
- Ruff lint configuration in pyproject.toml → 0 errors
- E722 bare except fixes across 21 files
- Dependency conflict resolution
- pytest CI stability patches

#### Provider-Agnostic Common Ingest Pipeline
- `common_ingest.py` - Shared by HotelRunner and Exely
- Raw Event Store → Idempotency Guard → Decision Engine → PMS Import
- Provider collection mapping for MongoDB

#### HotelRunner REST API Provider (DONE)
- Full API client with rate limiting (5 req/min, 250 req/day)
- Webhook Receiver: 3 endpoints (reservations, modifications, cancellations)
- Scheduled Pull: Cursor-based with safety window
- Room/Rate mapping, ARI push, delivery confirmation
- Frontend dashboard at /hotelrunner

#### Exely SOAP Provider (DONE - March 2026)
- **SOAP Client**: `exely_client.py` with WSSE Security Header auth
- **XML Builder**: `soap_builder.py` for OTA_ReadRQ, OTA_HotelAvailRQ, OTA_NotifReportRQ, OTA_HotelAvailNotifRQ
- **Response Parser**: `response_parser.py` with defusedxml for safe XML parsing
- **Normalizer**: `normalizer.py` converts Exely format to canonical PMS format
- **Pull Worker**: `exely_pull_worker.py` - cursor-based scheduled pull
- **API Router**: 15 endpoints for full lifecycle:
  - Connection: connect, test, disconnect, status
  - Room Discovery: OTA_HotelAvailRQ
  - Room Mapping: CRUD
  - ARI Push: single + bulk delta push
  - Reservation: manual pull, local list, delivery confirm
  - Sync: scheduler start/stop, status, logs
- **Frontend**: Full dashboard at /exely with 5 tabs
- **Testing**: 14/14 backend tests pass, frontend verified

## Prioritized Backlog

### P0 (Critical)
- None currently - all P0 items completed

### P1 (High)
- HotelRunner Sandbox Real Test (requires live credentials)
- Pilot Hotel Onboarding

### P2 (Medium)
- Enhanced mapping UI with drag-drop
- ARI push scheduling (auto-push based on PMS changes)
- Cross-provider reconciliation dashboard

### P3 (Low/Future)
- Additional provider integrations (SiteMinder, Channex)
- Multi-property channel manager aggregation
- Revenue-based auto-pricing for ARI pushes

## Key DB Collections
- `hotelrunner_connections`, `hotelrunner_reservations`, `hotelrunner_raw_events`, `hotelrunner_room_mappings`, `hotelrunner_sync_logs`, `hotelrunner_pull_cursors`
- `exely_connections`, `exely_reservations`, `exely_raw_events`, `exely_room_mappings`, `exely_sync_logs`, `exely_pull_cursors`

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
| GM User | gm@hotel.com | gm123 |
| Superadmin | super@hotel.com | super123 |
