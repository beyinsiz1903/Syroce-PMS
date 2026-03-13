# RoomOps PMS - Product Requirements Document

## Original Problem Statement
Full-stack Hotel Property Management System (PMS) SaaS platform with multi-provider Channel Manager integration. Current phase: event-driven ARI push pipeline and provider validation.

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

=== ARI PUSH ENGINE (P1 — NEW) ===
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
Outbound Push Queue (idempotent, rate-limited)
    ↓
Provider Adapter (HotelRunner | Exely)
    ↓
Ack / Retry / Error → Sync Log + Drift State
    ↓
Drift Worker (snapshot compare → corrective delta → push queue)
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
- **API**: 12 endpoints under /api/channel-manager/ari/*
- **Frontend**: ARIPushDashboard with Queue Monitor, Outbound Logs, Drift, Events tabs
- **Data Model**: 4 collections (ari_events, ari_change_sets, ari_outbound_logs, ari_drift_state)
- **Testing**: 30/30 backend tests pass, all frontend elements verified

## Prioritized Backlog

### P1 (Next)
- HotelRunner Sandbox real test (with live credentials)
- Exely real SOAP connection test (with live credentials)

### P2
- Channex REST provider (next provider)
- Reconciliation dashboard UI

### P3
- SiteMinder XML/OTA provider
- Multi-property channel manager aggregation
- ARI push with real provider credentials (post-sandbox validation)

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
| GM User | gm@hotel.com | gm123 |
| Superadmin | super@hotel.com | super123 |
