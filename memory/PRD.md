# RoomOps PMS - Product Requirements Document

## Original Problem Statement
Full-stack Hotel Property Management System (PMS) SaaS platform. Development phase declared complete. Current phase: operational validation and real-world integration testing.

## Current Phase: HotelRunner Integration

### Architecture
```
OTA (Booking.com / Expedia / Agoda)
    |
    v
HotelRunner (Channel Manager)
    |
    v
[Webhook Receiver] ─── Primary path
    |
    v
[Raw Event Store] ─── Audit + Replay
    |
    v
[Idempotency Guard] ─── Dedup by hr_number + channel
    |
    v
[Schema Normalizer] ─── HR format → Canonical PMS format
    |
    v
[Decision Engine] ─── create / update / cancel / skip / pending_mapping
    |
    v
[PMS ReservationService]

Fallback path:
[Scheduled Pull Job] → Cursor-based fetch → Same ingest pipeline
```

### What's Been Implemented (March 2026)

#### CI/CD Pipeline Fix
- Ruff lint configuration in pyproject.toml → 0 errors
- E722 bare except fixes across 21 files
- Dependency conflict resolution (locust/python-engineio/python-socketio)

#### HotelRunner REST API Provider
- Full API client with rate limiting (5 req/min, 250 req/day)
- Connection test, rooms fetch, ARI push, reservation pull
- Delivery confirmation, channel listing, transaction tracking

#### Enterprise Reservation Ingest Pipeline
- **Webhook Receiver**: 3 endpoints (reservations, modifications, cancellations)
  - Lightweight: receive → ack → background process
  - Tenant resolution via X-Tenant-ID header or hr_id lookup
- **Raw Event Store**: Every event persisted for replay and audit
- **Idempotency Guard**: Two-layer (reservation identity + event identity)
- **Schema Normalizer**: HotelRunner → canonical PMS format
- **Decision Engine**: create/update/cancel/skip/pending_mapping
- **Loop Prevention**: source_system + external_write_protected flags
- **Mapping Guard**: No auto-import without room mapping

#### Scheduled Pull Job
- Cursor-based with safety window (fetch last N+5 minutes)
- Auto-runs for all active connections
- Manual trigger endpoint

#### Frontend Dashboard
- HotelRunner Integration page at `/hotelrunner`
- 5 tabs: Baglanti, Odalar, Rezervasyonlar, Eslemeler, Loglar
- Connection form, room list, reservation table, mapping CRUD, sync logs

### Key API Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/api/channel-manager/hotelrunner/connect` | POST | Setup connection |
| `/api/channel-manager/hotelrunner/connection` | GET | Connection status |
| `/api/channel-manager/hotelrunner/test` | POST | Test connection |
| `/api/channel-manager/hotelrunner/rooms` | GET | Fetch rooms |
| `/api/channel-manager/hotelrunner/rooms/update` | PUT | ARI push |
| `/api/channel-manager/hotelrunner/rooms/bulk-update` | POST | Bulk ARI |
| `/api/channel-manager/hotelrunner/reservations` | GET | Fetch from HR |
| `/api/channel-manager/hotelrunner/reservations/sync` | POST | Sync all |
| `/api/channel-manager/hotelrunner/reservations/local` | GET | Local stored |
| `/api/channel-manager/hotelrunner/webhooks/reservations` | POST | Webhook: new |
| `/api/channel-manager/hotelrunner/webhooks/modifications` | POST | Webhook: modify |
| `/api/channel-manager/hotelrunner/webhooks/cancellations` | POST | Webhook: cancel |
| `/api/channel-manager/hotelrunner/sync/reservations/pull` | POST | Manual pull |
| `/api/channel-manager/hotelrunner/sync/status` | GET | Sync status |
| `/api/channel-manager/hotelrunner/sync/scheduler/start` | POST | Start scheduler |
| `/api/channel-manager/hotelrunner/sync/scheduler/stop` | POST | Stop scheduler |
| `/api/channel-manager/hotelrunner/logs/events` | GET | Raw events |
| `/api/channel-manager/hotelrunner/logs/errors` | GET | Error events |
| `/api/channel-manager/hotelrunner/room-mappings` | GET/POST/DELETE | Room mappings |
| `/api/channel-manager/hotelrunner/channels` | GET | HR channels |

### Key Files
- `/app/backend/domains/channel_manager/providers/hotelrunner.py` - API client
- `/app/backend/domains/channel_manager/providers/hotelrunner_router.py` - Connection/rooms/mappings
- `/app/backend/domains/channel_manager/providers/hotelrunner_ingest.py` - Ingest pipeline
- `/app/backend/domains/channel_manager/providers/hotelrunner_webhook.py` - Webhooks + scheduler
- `/app/frontend/src/pages/HotelRunnerIntegration.jsx` - Dashboard

### Testing Status
- iteration_58: Backend 5/5 (100%), Frontend 100% - basic endpoints
- iteration_59: Backend 16/16 (100%), Frontend 100% - webhook/ingest pipeline

## Prioritized Backlog

### P0 - Blocked on User
- HotelRunner sandbox credentials (TOKEN + HR_ID) from partner portal

### P0 - Next (when credentials arrive)
- Real connection test
- Room list fetch + room mapping
- Reservation pull test
- ARI push test

### P1
- ARI drift detection worker (2min interval)
- Webhook URL registration in HotelRunner panel
- Pilot Hotel Onboarding
- Canary Rollout Plan

### P2
- Advanced reconciliation UI
- Provider-specific anomaly alerts
- Weekly Incident Drills

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
| GM User | gm@hotel.com | gm123 |
| Superadmin | super@hotel.com | super123 |
| Test Tenant ID | 044f122b-87b5-480a-88b4-b9534b0c8c90 | - |
