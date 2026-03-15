# RoomOps PMS — Product Requirements Document

## Original Problem Statement
Build a production-grade hospitality platform. Initial phase: Cross-Provider Reconciliation Engine managing data inconsistencies between local PMS and two external channel managers (HotelRunner REST, Exely SOAP). Current phase: Operational Channel Monitoring, Alerting, and Production-Grade Provider Adapters.

## Architecture
- **Frontend:** React + Shadcn UI
- **Backend:** FastAPI + MongoDB
- **Providers:** HotelRunner (REST), Exely (SOAP)

## What's Been Implemented

### Phase 1 — Core Reconciliation Engine (Complete)
- Multi-provider data model (connections, room/rate mappings, lineage, ARI)
- Reservation ingest pipeline with normalization
- Reconciliation engine with snapshot comparison
- Data Model Dashboard with 7 tabs

### Phase 2 — Operational Monitoring & Alerting (Complete)
- Real-time health dashboard
- Alert engine with configurable thresholds
- Background monitoring worker

### Phase 3 — Production Readiness Tooling (Complete)
- Credential Configuration & Validation UI
- Pilot Go-Live Playbook (`/app/memory/PILOT_HOTEL_GO_LIVE_PLAYBOOK.md`)
- Slack Alert Integration
- Monitoring Trend Charts (24h)

### Phase 4 — HotelRunner Production-Grade Adapter (Complete — 2026-03-15)
12-module modular adapter consolidating two legacy implementations:

```
providers/hotelrunner/
  __init__.py          — Public API exports
  provider.py          — Main facade (HotelRunnerProvider)
  client.py            — HTTP client (timeout, logging, status mapping)
  auth.py              — Centralized query param auth
  endpoints.py         — API path constants
  schemas.py           — Request/response data contracts
  parser.py            — Safe response parsing with validation
  mapper.py            — Bidirectional canonical ↔ HR mapping
  paginator.py         — Pagination handler with safety guards
  retry.py             — Exponential backoff, retryable/non-retryable separation
  errors.py            — Typed error hierarchy (8 error classes)
  validators.py        — Pre-flight validation
  observability.py     — Metrics recording & health indicators
```

**Key Design Decisions:**
- Single source of truth for all HotelRunner API operations
- Legacy dict interface preserved for backward compatibility
- New ProviderResult-based interface for updated callers
- Error hierarchy maps to monitoring/alerting severity levels
- Comprehensive test suite: 96 tests (67 unit + 13 integration + 16 API)

**Wiring Points Updated:**
- `provider_config_router.py` → uses ProviderResult
- `hotelrunner_router.py` → uses ProviderResult
- `ingest/workers.py` → uses legacy dict interface (compatible)
- `snapshot_collectors.py` → uses legacy dict interface (compatible)
- `hotelrunner_ari_adapter.py` → uses legacy update_room (compatible)

**Deprecated:**
- `providers/hotelrunner_legacy.py` (was hotelrunner.py) — removal target: next major release
- `channel_manager/connectors/hotelrunner/` — removal target: next major release

## Prioritized Backlog

### P0 (Critical)
- [x] HotelRunner production-grade adapter — DONE
- [ ] Exely production-grade SOAP adapter (same 12-module pattern)
- [ ] Real API credentials integration + sandbox testing

### P1 (High)
- [ ] Mapping UI improvement (PMS rooms/rates ↔ provider rooms/rates)

### P2 (Medium)
- [ ] Legacy collection cleanup (archive unused MongoDB collections)
- [ ] Remove deprecated `hotelrunner_legacy.py` and `connectors/hotelrunner/`

### P3 (Low)
- [ ] 24h soak test
- [ ] Reservation burst test
- [ ] ARI storm test

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
