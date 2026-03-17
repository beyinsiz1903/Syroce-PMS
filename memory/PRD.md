# Syroce PMS — Product Requirements Document

## Original Problem Statement
Enterprise-grade PMS (Property Management System) with channel management, runtime enforcement, and operational visibility for the Turkish hospitality market. Focus on reliability, observability, and production readiness.

## Core Architecture
- **Backend:** FastAPI + MongoDB + Motor (async)
- **Frontend:** React + Tailwind + Shadcn/UI
- **Integrations:** Exely (SOAP), HotelRunner (REST), Slack (notifications)
- **Realtime:** Socket.IO for cockpit streaming

## User Personas
- **Hotel Operator:** Day-to-day PMS operations, reservations, ARI management
- **System Admin:** Runtime monitoring, incident response, rollout management

## Completed Phases

### P1-P3: Core Foundation
- Reservation management, room/rate mapping, ARI push/pull
- Channel Manager with Exely + HotelRunner providers
- Delta debounce, coalescing, provider simulation

### P4: Runtime Enforcement (47 tests)
- Hard Fail Gate with mapping enforcement
- Auto-Heal Service with conservative healing
- Push Loop Worker with delta processing
- Quarantine mechanism for failed items

### P5: Operational Visibility (26 tests)
- Notification System with severity model + cooldown
- Runtime Cockpit Dashboard (flight panel)
- Quarantine Visibility (classification + age buckets)

### P6: Production Readiness (15 tests) — COMPLETED 2026-03-17
- **Readiness Scorer:** Scored "Why NOT READY?" breakdown (0-100)
  - Weighted components: Mapping (40pts), Hard Fail (25pts), Verify (20pts), Drift (10pts), Quarantine (5pts)
  - Prioritized issues sorted by severity (BLOCKER > CRITICAL > WARNING > INFO)
  - Fix order suggestions with estimated impact scores
  - READY state transition logging with delta analysis
- **1-Click Safe Actions:** Idempotent operator actions
  - Retry Safe: Re-queue retryable failed change sets
  - Safe Release Quarantine: Guard chain (mapping validity + staleness)
  - Revalidate Mapping: Full validation with diff output
  - Suppress Noise: Temporary notification cooldown (max 120 min)
- **Narrow Rollout Framework:** Controlled live deployment
  - 5-phase state machine: INTERNAL → DUAL_PROVIDER → REAL_PILOT → 7DAY_PROOF → PRODUCTION
  - Strict automatic gate checks (no manual override)
  - Phase-specific criteria enforcement
  - Duration minimums per phase
- **WebSocket Cockpit Streaming:** Real-time snapshot-based updates
  - Critical metrics: verify_ratio, hard_fail_blocked, quarantine_count, drift_count, queue_size
  - Diff-based broadcasting (only sends changes)
  - LIVE indicator in UI

## Total Test Coverage
- P4: 47 tests
- P5: 26 tests
- P6: 15 tests
- **Total: 88 tests, all passing**

## Key API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/lockdown/runtime/cockpit | GET | Full cockpit metrics |
| /api/lockdown/runtime/readiness-score | GET | Scored readiness breakdown |
| /api/lockdown/runtime/actions/retry-safe | POST | Retry failed change sets |
| /api/lockdown/runtime/actions/revalidate-mapping | POST | Validate all mappings |
| /api/lockdown/runtime/actions/suppress-noise | POST | Suppress notifications |
| /api/lockdown/runtime/rollout/state | GET | Current rollout state |
| /api/lockdown/runtime/rollout/initialize | POST | Start rollout |
| /api/lockdown/runtime/rollout/gate-check | GET | Evaluate gate conditions |
| /api/lockdown/runtime/rollout/advance | POST | Attempt phase transition |
| /api/lockdown/runtime/rollout/dashboard | GET | Full rollout dashboard |
| /api/lockdown/notifications/events | GET | Recent events |
| /api/lockdown/notifications/summary | GET | Event summary by severity |

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |

## Prioritized Backlog
- (P0) Narrow Rollout Execution — actually run through phases in live env
- (P1) Advanced Auto-Heal — confidence score, provider-specific rules
- (P2) Deprecated Code Cleanup — hotelrunner.py, client.py, exely_client_legacy.py
- (P3) Core Lockdown Blocks B & C — ProviderCapabilityMatrix, Reconciliation Truth Table
- (P4) Financial Module Hardening — Folio, Night Audit
- (P4) Tenant Management — per-tenant rollout gates, feature flags
