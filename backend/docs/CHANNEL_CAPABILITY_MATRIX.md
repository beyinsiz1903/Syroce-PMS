# Channel Manager — Provider Capability Matrix

## Status: Living Document
## Last Updated: 2026-03

## Provider Overview

| Dimension | Exely | HotelRunner |
|-----------|-------|-------------|
| Protocol | SOAP/XML | REST/JSON |
| Integration Phase | Production | Production |
| Webhook Ingest | Yes | Yes |
| ARI Push (Outbox) | Yes | Yes |

## Reservation Ingest (OTA -> PMS)

| Capability | Exely | HotelRunner | Notes |
|------------|-------|-------------|-------|
| New reservation receive | Yes | Yes | Webhook -> ingest pipeline -> import bridge |
| Modification receive | Yes | Yes | Version-based dedup prevents stale overwrites |
| Cancellation receive | Yes | Yes | Status propagation to PMS state machine |
| Duplicate detection (provider event ID) | Yes | Yes | `provider_event_id` unique check |
| Duplicate detection (payload hash) | Yes | Yes | SHA-256 content hash as fallback |
| Stale version detection | Yes | Yes | Version field comparison |
| Normalization to canonical form | Yes | Yes | Unified `IngestEvent` model |
| Room mapping validation | Yes | Yes | `validated` stage in pipeline |
| Rate mapping validation | Yes | Yes | `validated` stage in pipeline |
| Raw payload storage | Yes (SOAP XML) | Yes (JSON) | 90-day TTL, correlation_id linked |
| End-to-end timeline tracing | Yes | Yes | webhook_received -> normalized -> deduplicated -> validated |
| Correlation ID propagation | Yes | Yes | From webhook entry through all pipeline stages |
| Error classification | Yes | Yes | 5-type failure taxonomy in FailureTracker |

## ARI Distribution (PMS -> OTA)

| Capability | Exely | HotelRunner | Notes |
|------------|-------|-------------|-------|
| Availability push | Yes | Yes | Via outbox pattern |
| Rate push | Yes | Yes | Via outbox pattern |
| Inventory push | Yes | Yes | Via outbox pattern |
| Outbox reliable delivery | Yes | Yes | Retry with exponential backoff |
| Batch ARI update | Partial | Yes | HotelRunner has native batch API |
| Rate plan sync | Partial | Yes | |
| Stop sale | Partial | Partial | Basic support, needs edge testing |

## Cancel/Modify Edge Coverage

| Scenario | Exely | HotelRunner | Status |
|----------|-------|-------------|--------|
| Cancel confirmed reservation | Yes | Yes | Tested in battle tests |
| Cancel already-cancelled (idempotent) | Yes | Yes | Double-cancel handled gracefully |
| Modify dates (extend stay) | Yes | Yes | Re-locks new nights atomically |
| Modify dates (shorten stay) | Yes | Yes | Releases freed nights |
| Modify room type | Partial | Partial | Needs deferred assignment (Phase C.3) |
| Cancel after check-in | Yes | Yes | Handled by state machine |
| Concurrent cancel + modify race | Yes | Yes | Optimistic locking (_version field) |

## Reconciliation & Data Integrity

| Capability | Exely | HotelRunner | Status |
|------------|-------|-------------|--------|
| Room-night lock reconciliation | Yes | Yes | Background worker every 5min |
| Drift detection | Yes | Yes | event_timeline alerts on mismatch |
| Inventory materialized view | Yes | Yes | Phase C.1 implemented (ADR-003) |
| Outbox stuck event detection | Yes | Yes | Control plane dashboard |
| Import bridge failure tracking | Yes | Yes | FailureTracker with structured taxonomy |

## Gaps & Planned Work

| Gap | Impact | Target Phase | Priority |
|-----|--------|--------------|----------|
| Channel-level inventory allotments | Cannot set per-OTA room limits | Phase C.3 | P1 |
| Deferred room assignment | Room assigned at ingest, not at check-in | Phase C.3 | P1 |
| Push latency SLO monitoring | No formal latency tracking for ARI pushes | Telemetry sprint | P2 |
| Rate plan parity (Exely) | Exely rate sync less mature than HotelRunner | Channel hardening | P2 |
| Reconciliation reporting | No dashboard for reconciliation results | Governance Phase 3 | P2 |
| Connection health monitoring | Provider connectivity not actively monitored | Ops sprint | P2 |
| Capability auto-discovery | No runtime feature negotiation with providers | Future | P3 |

## Production Readiness Checklist

| Criteria | Exely | HotelRunner |
|----------|-------|-------------|
| Ingest pipeline battle-tested | Yes (10+ battle tests) | Yes (10+ battle tests) |
| ARI push verified | Yes (outbox tests) | Yes (outbox tests) |
| Error recovery tested | Yes (retry engine) | Yes (retry engine) |
| Raw payload audit trail | Yes (90d retention) | Yes (90d retention) |
| Timeline traceability | Yes (<1s lookup) | Yes (<1s lookup) |
| CI hard gate coverage | Yes | Yes |
| Sandbox/staging tested | Pending | Pending |
| Live pilot hotel tested | Pending | Pending |
| Cancel/modify edge coverage | 6/7 scenarios | 6/7 scenarios |
| Push latency SLO defined | Not yet | Not yet |
