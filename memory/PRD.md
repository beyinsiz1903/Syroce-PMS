# Syroce PMS — Product Requirements Document

## Original Problem Statement
Full-stack PMS/channel manager production hardening. The system manages hotel reservations, room/rate mappings, ARI (Availability, Rates, Inventory) pushes to external providers (Exely, HotelRunner), and operational observability.

## Core Architecture
- **Backend:** FastAPI + MongoDB
- **Frontend:** React (Vite) + Shadcn/UI + Tailwind
- **Providers:** Exely (SOAP), HotelRunner (REST)

## Completed Phases

### P1 — Domain Truth & Folio Fix (COMPLETED)
- Canonical reservation lifecycle with strict state transitions
- Navigation/Folio bug fix
- Observability endpoints (`/api/lockdown/*`)
- 48 regression tests

### P2 — Stress Testing & Observability (COMPLETED)
- Replay safety test suite (24 tests)
- Duplicate storm test suite (14 tests)
- ARI stress test suite (43 tests)
- Lockdown Dashboard frontend (`/lockdown`)
- Total: 129 tests passing

### P3 — Delta Correctness, Provider Resilience & Incident Panel (COMPLETED — 2026-03-17)
- **Delta-Only Push + Debounce Correctness (50 tests):**
  - Fixed coalescer `_merge_date_ranges` with `_deduplicate_by_date_range` for last-write-wins
  - Multi rate changes → only final value pushed
  - Inventory + restriction simultaneous changes → separate deltas
  - close/open/close restriction pattern → close wins
  - Intermediate state loss prevention
  - Outbound idempotency hash (same data not re-pushed)
  - Burst → correct final payload
  - Cross-room isolation, rate plan scoping
  - End-to-end pipeline correctness
- **Real Provider Simulation (63 tests):**
  - 429 rate limiting → token drain, retryable
  - Timeout → retryable with backoff
  - Intermittent 200/500 → retry until success
  - Delayed ACK / ACK-but-no-apply semantics
  - Permanent failures (400, 401, 403, 422)
  - Connection errors → retryable
  - Retry exhaustion → manual_review
  - Provider error classification accuracy
  - Rate limiter service correctness
  - Outbound log audit trail
- **Operator Incident Panel:**
  - Backend API: `/api/ops/incidents/summary`, `/list`, `/action/{id}`, `/detail/{id}`
  - Frontend: `/incidents` route with summary cards, filters, incident list, action buttons
  - Supports retry, review, resolve, suppress actions with audit trail
  - Shows enriched data: recommended_action, can_auto_heal, gold_source
- **Total: 242 tests passing (zero regressions)**

## Key Technical Decisions
- Coalescer uses "last write wins" for overlapping date ranges (P3 fix)
- All providers: `ack_means_applied = False` → drift detection required
- Restriction precedence: `close > open` (safety-first)
- Outbound delta hash prevents re-pushing identical data
- Incident panel uses `/api/ops/incidents/*` prefix (separate from existing `/api/incidents/*`)

## Test Coverage
| Suite | Tests | File |
|-------|-------|------|
| P1 Core Lockdown | 48 | `test_core_lockdown.py` |
| P2 Replay Safety | 24 | `test_p2_replay.py` |
| P2 Duplicate Storm | 14 | `test_p2_duplicate_storm.py` |
| P2 ARI Stress | 43 | `test_p2_ari_stress.py` |
| P3 Delta-Debounce | 50 | `test_p3_delta_debounce.py` |
| P3 Provider Simulation | 63 | `test_p3_provider_simulation.py` |
| **Total** | **242** | |

## Upcoming Tasks (Priority Order)

### P4 — Remaining Hardening
1. **Reconciliation Truth Table** auto-healing vs. manual review workflows
2. **Hard Fail logic** for incomplete/ambiguous mappings
3. **Delta-only push + debounce** runtime implementation (tests exist, runtime debounce loop next)

### P5 — Financial Hardening
- Folio and Night Audit modules
- Per-tenant rollout gates and feature flags

### Backlog
- PMS room/rate → provider mapping UI improvement
- Archive old database collections
- Remove deprecated files (`hotelrunner.py`, `client.py`, `exely_client_legacy.py`)
- Slack notifications for go-live acceleration events

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
