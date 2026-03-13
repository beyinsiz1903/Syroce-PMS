# CHANGELOG

## 2026-03-13 — 9-Collection Data Model (v2.0)
- Implemented optimized 9-collection data model for 2-provider architecture (HotelRunner + Exely)
- Created `data_model.py` with Pydantic models: ProviderConnection, RoomMapping, RatePlanMapping, RawChannelEvent, ReservationLineage, ReconciliationCase
- Created `unified_repository.py` with full CRUD operations, tenant isolation, MongoDB indexes
- Created `model_router.py` with 25+ REST endpoints under `/api/channel-manager/model/`
- Created `DataModelDashboard.jsx` frontend with 6 tabs: Connections, Room Mappings, Rate Mappings, Lineage, Raw Events, Reconciliation
- ConnectorProvider enum restricted to `hotelrunner | exely`
- Testing: 29/29 backend tests passed, all frontend features verified

## 2026-03-12 — Architectural Enhancements
- Enriched Delta Hash for outbound idempotency
- Dual-Mode Drift Worker (Normal/Recovery)
- Provider Test Harness scaffolding
- Dashboard Metrics (provider health, latency, queue stats)
