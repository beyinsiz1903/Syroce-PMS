# CHANGELOG

## 2026-03-13 — Reservation Ingest Pipeline
- Implemented production-grade 8-stage ingest pipeline: persist → dedup → hash → stale → normalize → mapping → decide → lineage
- Created `ingest/normalizer.py` with HotelRunner + Exely payload normalization and identity extraction
- Created `ingest/decision_engine.py` with 6 decision outcomes: create, update, cancel, skip, pending_mapping, manual_review
- Created `ingest/pipeline.py` with full async pipeline processing
- Created `ingest/workers.py` with 4 workers: HR pull (stub), Exely pull (stub), ingest processor, replay worker
- Created `ingest/ingest_router.py` with monitoring/control API (inject, inject-and-process, worker triggers, status)
- Updated `hotelrunner_webhook.py` to feed webhooks into unified ingest pipeline
- Updated `data_model.py` with ProcessingStatus enum, enhanced ReservationLineage (decision tracking, timestamps), new CaseTypes
- Updated `unified_repository.py` with ingest-specific queries (dedup check, hash check, failed events, event stats)
- Updated `DataModelDashboard.jsx` with Ingest Pipeline tab: worker controls, raw events table, processing badges
- Testing: 24/24 backend tests passed, all 8 pipeline stages verified, all frontend features working

## 2026-03-13 — 9-Collection Data Model (v2.0)
- Implemented optimized 9-collection model for 2-provider architecture
- ConnectorProvider enum: hotelrunner | exely
- 29/29 backend tests passed

## 2026-03-12 — Architectural Enhancements
- Enriched Delta Hash, Dual-Mode Drift Worker, Provider Test Harness, Dashboard Metrics
