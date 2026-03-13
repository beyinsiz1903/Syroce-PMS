# RoomOps PMS - Product Requirements Document

## Original Problem Statement
Full-stack Hotel Property Management System (PMS) SaaS platform with multi-provider Channel Manager integration. Current phase: event-driven ARI push pipeline refinement and provider validation preparation.

## Architecture
```
OTA (Booking.com / Expedia / Agoda)
    |
    v
Channel Manager Providers:
  ├── HotelRunner (REST API) ─── [Webhook + Scheduled Pull]
  ├── Exely (SOAP/OTA)     ─── [Scheduled Pull via OTA_ReadRQ]
  └── (Future: Channex, SiteMinder)
    |
    v
[Raw Event Store] ─── Audit + Replay + payload_hash
    |
    v
[Versioned Decision Engine]
    ├── Idempotency Guard (UniqueID + LastModifyDateTime + payload_hash)
    │   ├── newer LastModifyDateTime → update
    │   ├── same time + same hash → skip (duplicate)
    │   ├── cancelled status → cancel (always wins)
    │   └── older LastModifyDateTime → discard (stale)
    ├── Room Mapping Check
    └── PMS Import with lineage tracking
    |
    v
[Reservation Record]
    ├── source_provider         (reconciliation-ready)
    ├── provider_event_id       (audit trail)
    ├── provider_version        (incremented on update)
    ├── provider_last_modified_at (version comparison)
    ├── provider_payload_hash   (duplicate detection)
    └── confidence_score        (future: ML scoring)

=== ARI PUSH ENGINE (P1 — COMPLETE) ===
PMS Service (FrontDesk, Pricing, Housekeeping...)
    ↓
ARI Domain Event (availability | rate | restriction)
    ↓
ARI Event Buffer (in-memory, per-type debounce: avail=2s, rate=5s, restriction=3s)
    ↓
Coalescer (same-key merge, date-range merge, last-write-wins, restriction precedence)
    ↓
Delta Compiler (provider-specific: HR→REST params, Exely→SOAP periods)
    ↓
Outbound Push Queue (idempotent with enriched 7-field delta hash, rate-limited)
    ↓
Provider Adapter (HotelRunner | Exely)
    ↓
Ack / Retry / Error → Sync Log + Drift State
    ↓
Drift Worker (dual-mode: normal 2min/changed, recovery 30s/full)
```

## What's Been Implemented

### CI/CD Pipeline Fix (March 2026) - DONE
### HotelRunner REST API Provider - DONE
### Exely SOAP Provider - DONE
### Reservation Versioning (P0) - DONE
### WSSE Security Hardening (P0) - DONE
### Provider Lineage Fields (P0) - DONE

### P1: Event-Driven ARI Push Engine - DONE (Feb 2026)
- **Event Contract**: Canonical ARIChangeEvent model for all PMS services
- **Buffer + Debounce**: In-memory buffer with per-event-type debounce (2s/3s/5s)
- **Coalescer**: Same-key merge, date-range merge, last-write-wins, restriction precedence (close>open)
- **Delta Compiler**: Provider-specific compilation (HotelRunner REST, Exely SOAP)
- **Outbound Service**: Full push orchestration with idempotency, rate limiting, ack handling
- **Rate Limiter**: Per-provider per-property token bucket (HotelRunner: 5rpm/250daily, Exely: 30rpm/5000daily)
- **Retry Policy**: 5-level exponential backoff (0s→10s→30s→2min→5min), error classification
- **Ack Service**: Success/retry/dead-letter classification with outbound logging
- **Drift Worker**: Snapshot comparison + corrective delta generation + alert system
- **Provider Adapters**: HotelRunner + Exely (currently DRY-RUN mode)
- **API**: 12+ endpoints under /api/channel-manager/ari/*
- **Frontend**: ARIPushDashboard with Queue Monitor, Outbound Logs, Drift, Events, Test Harness tabs
- **Data Model**: 4 collections (ari_events, ari_change_sets, ari_outbound_logs, ari_drift_state)
- **Testing**: 30/30 backend + 17/17 v2 tests pass

### P1.1: ARI Engine Hardening (March 2026) - DONE
- **Enriched Delta Hash**: 7-field composite hash (provider, property_id, room_type, rate_plan, date_from, date_to, payload) for outbound idempotency, retry dedup, and drift comparison
- **Provider Test Harness**: Validation checklists for HotelRunner (9 steps) and Exely (6 steps) with DRY-RUN and live mode
- **Drift Worker Dual-Mode**: Normal (2min interval, changed rooms) and Recovery (30s interval, full property) with API toggle
- **Operational Metrics**: Provider health (ack_rate, error_rate, retry_rate), latency percentiles (p50/p95/p99), queue stats (depth, retry backlog, dead letters)
- **Dashboard Enhancement**: All metrics visualized in operational cards, Test Harness tab, drift mode toggle badge
- **Testing**: 17/17 backend tests pass, frontend fully verified

## Prioritized Backlog

### P0 (User decision needed)
- Channel Manager data model refinement (user to share "world's most robust CM data model")

### P1 (Next)
- HotelRunner Sandbox real test (with live credentials)
- Exely real SOAP connection test (with live credentials)

### P2
- Channex REST provider (next provider)
- Mapping UI improvement
- Reconciliation engine

### P3
- SiteMinder XML/OTA provider
- Multi-property channel manager aggregation
- Advanced ARI UI (Change Set Viewer, manual resync controls)

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
| GM User | gm@hotel.com | gm123 |
| Superadmin | super@hotel.com | super123 |

## Key API Endpoints (ARI)
- `POST /api/channel-manager/ari/events/publish` - Publish ARI change event
- `GET /api/channel-manager/ari/change-sets` - View change sets
- `POST /api/channel-manager/ari/push` - Push pending changes
- `GET /api/channel-manager/ari/outbound-logs` - Audit provider communication
- `GET /api/channel-manager/ari/drift` - View drift states
- `GET /api/channel-manager/ari/drift/mode` - Get drift mode
- `POST /api/channel-manager/ari/drift/mode/{mode}` - Toggle drift mode
- `GET /api/channel-manager/ari/test-harness/checklist/{provider}` - Get validation checklist
- `POST /api/channel-manager/ari/test-harness/run/{provider}` - Run provider tests
- `GET /api/channel-manager/ari/test-harness/metrics` - Operational metrics
- `GET /api/channel-manager/ari/stats` - Aggregate stats
- `GET /api/channel-manager/ari/engine-stats` - Runtime engine stats
