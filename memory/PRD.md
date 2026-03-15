# RoomOps PMS — Product Requirements Document

## Original Problem Statement
The user, a technical architect, aims to build a production-grade hospitality platform (PMS + Channel Manager). The current phase focuses on replacing all mocked data provider integrations with real, robust, and maintainable API adapters.

## User Personas
- **Hotel Technical Architect**: Manages the platform, configures provider integrations
- **Hotel Operations Staff**: Uses dashboards for reservations, room management, ARI

## Core Requirements
1. **(P0) Real Provider Integrations** — Replace mocked code with production-grade adapters
2. **(P1) Mapping UI Improvement** — Enhance PMS room/rate ↔ Provider room/rate mapping UI
3. **(P2) Legacy Collection Cleanup** — Archive/delete unused database collections

## What's Been Implemented

### Phase 1: HotelRunner (REST) Adapter — COMPLETE ✅
- 12-module production-grade adapter at `/app/backend/domains/channel_manager/providers/hotelrunner/`
- Modules: auth, client, endpoints, errors, mapper, observability, paginator, parser, provider, retry, schemas, validators
- 67 unit tests + 13 integration tests (80 total)
- All call sites consolidated to use single provider facade

### Phase 2: Exely (SOAP) Adapter — COMPLETE ✅ (2026-03-15)
- Production-grade adapter at `/app/backend/domains/channel_manager/providers/exely/`
- New modules: errors.py, retry.py, observability.py, validators.py, client.py, provider.py, __init__.py
- Existing modules preserved: soap_builder.py, response_parser.py, normalizer.py
- 77 unit tests + 14 integration tests (91 total)
- All call sites updated: exely_router.py, exely_pull_worker.py, provider_config_router.py, snapshot_collectors.py, ingest/workers.py
- Old ExelyClient deprecated to exely_client_legacy.py
- Full backward compatibility via legacy_* methods

### Deployment Fix (2026-03-15)
- Fixed `requirements.txt` to include `--extra-index-url` for `emergentintegrations` package

## Test Summary
| Suite | Tests | Status |
|-------|-------|--------|
| Exely Unit Tests | 77 | ✅ PASS |
| Exely Integration Tests | 14 | ✅ PASS |
| HotelRunner Unit Tests | 67 | ✅ PASS |
| Existing Exely API Tests | 37 | ✅ PASS |
| **Total** | **195+** | **✅ ALL PASS** |

## Prioritized Backlog

### P1 — Mapping UI Improvement
- Enhance the UI for mapping PMS rooms/rates to provider rooms/rates

### P2 — Legacy Collection Cleanup
- Archive or delete old, unused database collections
- Remove deprecated HotelRunner files after stabilization

### P3 — Production Readiness
- 24h soak test, reservation burst test, ARI storm test
- ML library optimization for deployment (scikit-learn, xgboost)

## Architecture
```
/app/backend/domains/channel_manager/providers/
├── hotelrunner/          # Production REST Adapter (COMPLETE)
│   ├── auth.py, client.py, endpoints.py, errors.py
│   ├── mapper.py, observability.py, paginator.py
│   ├── parser.py, provider.py, retry.py
│   ├── schemas.py, validators.py
│   └── __init__.py
├── exely/                # Production SOAP Adapter (COMPLETE)
│   ├── errors.py, retry.py, observability.py
│   ├── validators.py, client.py, provider.py
│   ├── soap_builder.py, response_parser.py
│   ├── normalizer.py, exely_router.py
│   ├── exely_pull_worker.py
│   ├── exely_client_legacy.py (DEPRECATED)
│   └── __init__.py
```

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
