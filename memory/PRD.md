# Syroce PMS — Product Requirements Document

## Overview
Full-stack PMS (Property Management System) integrated with Exely and HotelRunner channel managers.

## Core Architecture
- **Backend**: FastAPI + MongoDB
- **Frontend**: React with Shadcn UI
- **Providers**: Exely (SOAP API), HotelRunner (REST API)
- **Auth**: JWT-based

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |

---

## Core Lockdown Status (Production-Grade)

### P1 — Completed (2026-03-17)

#### 1. Folio Bug Fix
- Added `GET /api/folio/booking/{booking_id}` endpoint
- Fixed "View Folio" button to navigate correctly from reservation sidebar/calendar to folio detail view
- Button text translated to Turkish ("Folyo'yu Goruntule")

#### 2. Reservation Lifecycle Hardening
- **Canonical State Model**: `pending → confirmed → modified → cancelled → checked_in → checked_out → no_show`
- **Mutation Type Taxonomy**: `new_booking, partial_modification, date_change, room_type_change, rate_change, guest_detail_change, cancellation, reinstatement`
- **State Transition Rules**: Formal matrix with valid/invalid transitions (same-state allowed)
- **Event Idempotency**: `decision_version`, `decision_result`, `decision_reason` tracked on raw events
- **Out-of-Order Handling**: `provider_timestamp` vs `received_timestamp` vs `processed_at` separation, stale rejection policy
- **Concurrency Control**: Reservation-scoped optimistic locking with TTL (30s), lock_holder/lock_acquired_at/lock_expires_at
- **Raw Event Trace Enrichment**: `trace_id`, `normalization_result`, `decision_result`, `canonical_hash`, `raw_payload_hash`

#### 3. Mapping Completeness Hard Fail
- **Silent fallback prohibited**: Unmapped/inactive/ambiguous/deleted mappings cause HARD FAIL
- **Structured errors**: Each mapping failure produces `error_code`, `reason`, `operator_action_hint`
- **Mapping Health Score**: Per-provider completeness %, broken/inactive/ambiguous counts, `is_production_ready` flag

#### 4. Provider Capability Matrix
- **Behavioral contracts** for Exely and HotelRunner (not just config)
- Covers: ingest type, cancellation behavior, modification behavior, ARI push behavior, consistency window, rate limits
- **Error Classification**: `retryable` / `configuration` / `business_rejection`
- **Retry Policy**: Exponential backoff with max attempts, dead letter awareness
- **Delivery Confirmation States**: `queued → sent → acknowledged → accepted → applied → verified → failed`

#### 5. Reconciliation Truth Table
- **Gold source definitions**: raw_events (immutable), lineage (derived), ari_state (applied), mappings (config), provider (external)
- **Drift Taxonomy**: `missing_locally/remotely, stale_locally/remotely, status_mismatch, financial_mismatch, payload_mismatch, mapping_mismatch`
- **Resolution Policy**: `safe_auto_heal`, `risky_auto_heal`, `manual_review` per drift type

#### 6. Observability Endpoints
- `GET /api/lockdown/status` — System health check (ingest, mapping, reconciliation)
- `GET /api/lockdown/providers/capabilities` — Full provider capability matrix
- `GET /api/lockdown/reconciliation/truth-table` — Drift resolution rules
- `GET /api/lockdown/health/mapping` — Mapping health per provider
- `GET /api/lockdown/metrics/ingest` — Pipeline metrics (success/duplicate/stale/failure rates)
- `GET /api/lockdown/metrics/lineage` — Reservation lineage by status/provider
- `GET /api/lockdown/metrics/reconciliation` — Case metrics with age tracking
- `GET /api/lockdown/trace/reservation/{ext_id}` — End-to-end reservation trace

#### 7. Regression Test Suite
- **48 unit tests** covering decision engine, mutation detection, state transitions, provider capabilities, reconciliation truth, mapping validation
- **34 API tests** covering all lockdown endpoints

---

## P2 — Next (Upcoming)
- ARI Engine stress tests (10x burst, property-wide restriction push)
- Replay tests (last 24h events replay → same output)
- Duplicate storm tests (5-20x same event → single final state)
- Operator incident panel (affected property, provider, reservation IDs, recommended action)
- ARI delta-only push + debounce correctness

## P3 — Future
- Folio/night audit sertlestirme (append-only ledger, posting integrity, invoice immutability)
- Rollout gating + feature flags
- Pilot hotel proof pack (7-day sorunsuz)
- Safe mode (property bazli push durdurma)
- Legacy collection cleanup
- Deprecated provider file removal (hotelrunner.py, client.py, exely_client_legacy.py)

---

## Previous Completed Work
- Rate Manager UI redesign (light theme, consistent with Channel Manager)
- Rate Manager bulk update form (rates, availability, restrictions)
- Exely ARI push fix (split into two SOAP calls: price + availability)
- WebSocket error investigation (benign dev-only artifact)
