# RoomOps PMS - Product Requirements Document

## Original Problem Statement
Full-stack Hotel Property Management System (PMS) SaaS platform with multi-provider Channel Manager integration. Current phase: multi-provider expansion and integration validation.

## Architecture
```
OTA (Booking.com / Expedia / Agoda)
    |
    v
Channel Manager Providers:
  ├── HotelRunner (REST API) ─── [Webhook + Scheduled Pull]
  └── Exely (SOAP/OTA)     ─── [Scheduled Pull via OTA_ReadRQ]
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
```

## What's Been Implemented

### CI/CD Pipeline Fix (March 2026) - DONE
### HotelRunner REST API Provider - DONE
### Exely SOAP Provider - DONE
### Reservation Versioning (P0) - DONE
- Decision engine uses `UniqueID + LastModifyDateTime + payload_hash` for full version control
- Stale events discarded, duplicates detected, cancellations always win

### WSSE Security Hardening (P0) - DONE
- `wsu:Timestamp` with Created + Expires (5min TTL)
- `wsse:Nonce` with 16-byte random Base64Binary
- `wsse:Password` with PasswordText type attribute
- `soapenv:mustUnderstand="1"` on Security element

### Provider Lineage Fields (P0) - DONE
- `source_provider`, `provider_event_id`, `provider_version`
- `provider_last_modified_at`, `provider_payload_hash`
- `confidence_score` (placeholder for future ML)
- Applied to both HotelRunner and Exely normalizers

## Prioritized Backlog

### P1 (Next)
- Event-driven ARI push model (inventory_change_event → queue → provider ARI adapter)
- Delta compaction + coalescing/debounce
- Provider rate limit awareness
- drift_worker fallback

### P2
- HotelRunner Sandbox real test (with live credentials)
- Exely real SOAP connection test

### P3
- Channex REST provider (next provider)
- Reconciliation dashboard UI
- SiteMinder XML/OTA provider
- Multi-property channel manager aggregation

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |
| GM User | gm@hotel.com | gm123 |
| Superadmin | super@hotel.com | super123 |
