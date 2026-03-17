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
- **Delta-Only Push + Debounce Correctness (50 tests)**
- **Real Provider Simulation (63 tests)**
- **Operator Incident Panel** (Backend API + Frontend dashboard)
- **Total: 242 tests passing (zero regressions)**

### P4 — Runtime Enforcement (COMPLETED — 2026-03-17)
- **Hard Fail Gate (14 tests):**
  - Runtime mapping enforcement before ANY ARI push
  - Quarantines change sets with missing/broken mappings
  - Creates incidents with operator action hints
  - Duplicate incident prevention
  - Quarantine release after mapping fix
  - Integrated into outbound_service.py push pipeline
- **Auto-Heal Service (16 tests):**
  - Conservative auto-healing workflow based on Truth Table
  - Safe whitelist: stale_locally, stale_remotely
  - Risky whitelist (opt-in): payload_mismatch
  - Evidence trail for every heal operation
  - Failed heal escalation to manual review
  - Rate-limited cycles (max N per cycle)
- **Push Loop Worker (12 tests):**
  - Background runtime push loop with start/stop/pause/resume
  - Full observability: queued, coalesced, dropped, hard_fail_blocked, emitted, verify_success/fail
  - Per-provider ack latency tracking
  - Cycle count and timing metrics
- **Runtime Enforcement Router:**
  - `GET /api/lockdown/runtime/hard-fail/stats`
  - `POST /api/lockdown/runtime/hard-fail/release`
  - `GET /api/lockdown/runtime/auto-heal/stats`
  - `POST /api/lockdown/runtime/auto-heal/run`
  - `GET /api/lockdown/runtime/auto-heal/history`
  - `GET /api/lockdown/runtime/push-loop/status`
  - `POST /api/lockdown/runtime/push-loop/start`
  - `POST /api/lockdown/runtime/push-loop/stop`
  - `POST /api/lockdown/runtime/push-loop/pause`
  - `POST /api/lockdown/runtime/push-loop/resume`
  - `GET /api/lockdown/runtime/push-loop/metrics`
- **Integration tests (5 tests):** Combined behavior across all three layers
- **Total: 289 tests passing (zero regressions)**

## Key Technical Decisions
- Hard Fail Gate blocks pushes at runtime, not just in tests
- Auto-heal starts conservative (safe whitelist only), risky requires explicit opt-in
- Every auto-heal produces evidence before modifying data
- Failed auto-heals escalate (never infinite retry loop)
- Push loop worker is controllable (start/stop/pause/resume) for safe rollout
- Per-provider latency tracking for operational visibility

## Test Coverage
| Suite | Tests | File |
|-------|-------|------|
| P1 Core Lockdown | 48 | `test_core_lockdown.py` |
| P2 Replay Safety | 24 | `test_p2_replay.py` |
| P2 Duplicate Storm | 14 | `test_p2_duplicate_storm.py` |
| P2 ARI Stress | 43 | `test_p2_ari_stress.py` |
| P3 Delta-Debounce | 50 | `test_p3_delta_debounce.py` |
| P3 Provider Simulation | 63 | `test_p3_provider_simulation.py` |
| P4 Runtime Enforcement | 47 | `test_p4_runtime_enforcement.py` |
| **Total** | **289** | |

## Upcoming Tasks (Priority Order)

### P5 — Go-Live Acceleration
1. **Dashboard Notifications** (Slack/webhook) for critical state transitions:
   - `READY → NOT READY` (highest priority)
   - `NOT READY → READY`
   - mapping_completeness_reached_100
   - hard_fail_count_reached_0
   - first_successful_verify
   - drift_backlog_above_threshold
   - provider_auth_became_invalid
2. **Narrow rollout with internal tenant** — observation window before expanding

### P6 — Financial Hardening
- Folio and Night Audit modules
- Per-tenant rollout gates and feature flags

### Backlog
- PMS room/rate → provider mapping UI improvement
- Archive old database collections
- Remove deprecated files (`hotelrunner.py`, `client.py`, `exely_client_legacy.py`)
- Runtime Enforcement frontend dashboard

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
