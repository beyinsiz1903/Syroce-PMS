# Syroce PMS — Changelog

## 2026-03-22: Webhook Timeline Integration — End-to-End Traceability

### Exely Webhook Timeline
- Modified `providers/exely/exely_webhook_router.py` — Added timeline stages: webhook_received, normalized, deduplicated
- Raw SOAP XML payload stored in `webhook_raw_payloads` collection with correlation_id linkage
- Metadata includes: raw_payload_id, hotel_code, echo_token, source_ip, payload_size_bytes, content_type
- Duplicate detection writes: is_duplicate, is_new, matched_count, decision

### HotelRunner Webhook Timeline
- Modified `providers/hotelrunner_webhook.py` — Added timeline stage: webhook_received + raw payload storage
- Raw JSON payload stored in `webhook_raw_payloads` collection
- Correlation_id generated at webhook entry and propagated to ingest pipeline

### Ingest Pipeline Timeline
- Modified `domains/channel_manager/ingest/pipeline.py` — Added timeline stages at 4 key points:
  - Stage 2/3: `deduplicated` (provider_event_id duplicate, payload hash duplicate, or unique)
  - Stage 4: `deduplicated` (stale version detection)
  - Stage 5: `normalized` (canonical form with guest/room/rate/amount metadata)
  - Stage 6: `validated` (room_mapped, rate_mapped, mapping_target)
- Correlation_id propagation from webhook through all pipeline stages

### Raw Payload Storage & API
- New collection `webhook_raw_payloads` with 4 indexes (correlation, tenant+ext, provider, TTL 90d)
- New endpoints in timeline_router.py:
  - `GET /api/ops/timeline/raw-payload/{correlation_id}` — Single raw payload
  - `GET /api/ops/timeline/raw-payloads/by-external/{external_id}` — All payloads for a reservation
- Updated gap detection stages in timeline_reader.py

### Testing
- 18 API tests all passing (test_webhook_timeline_integration.py)
- Full end-to-end trace verified: webhook_received → normalized → deduplicated → validated
- Duplicate detection verified for both providers
- Raw payload storage verified for SOAP XML and JSON

---

## 2026-03-22: Core Battle Loop — Week 1 MVP

### Event Timeline System
- Created `controlplane/timeline_writer.py` — TimelineWriter with fire-and-forget `append()` 
- Created `controlplane/timeline_reader.py` — TimelineReader with entity/correlation/external_id lookup, search, gap detection
- Created `controlplane/timeline_router.py` — 5 API endpoints under `/api/ops/timeline/*`
- Added `event_timeline` collection with 5 indexes (entity, correlation, external_id, stage_health, TTL 90d)
- Registered timeline router in `bootstrap/router_registry.py`
- Added timeline indexes to `startup.py`

### FailureTracker Wiring
- Modified `core/import_bridge_service.py` — FailureTracker + Timeline at import_decided, stored, queued, failure stages
- Modified `core/outbox_worker.py` — FailureTracker + Timeline at dispatched, confirmed, failure stages
- Both use fire-and-forget pattern (failures are logged but never block main flow)

### Dashboard Aggregator
- Created `controlplane/dashboard_aggregator.py` — DashboardAggregator (8 parallel queries), health score algorithm, DashboardSnapshotWorker
- Created `controlplane/dashboard_router.py` — 5 API endpoints under `/api/ops/dashboard/*`
- Added `cp_health_snapshots` collection with 3 indexes (tenant, type, TTL 7d)
- Snapshot worker runs every 60s, started in `startup.py`

### Testing
- 21 API tests all passing (test_timeline_dashboard_api.py)
- Reservation trace: <1 second (goal was <5 seconds)
- Dashboard response: <500ms

---

## 2026-02-15: Battle-Readiness Blueprint
- Created 2576-line execution blueprint (`BATTLE_READINESS_BLUEPRINT.md`)
- 10-section production evolution plan with data models, APIs, workflows

## Earlier (pre-fork history)
- OPS-001: Control Plane (15 endpoints, failure taxonomy, retry engine, runbooks)
- CHAOS-001: Resilience testing (69 tests, 7 test files)
- Production infrastructure (crypto, secrets, tenant isolation, etc.)
