# Syroce PMS — Product Requirements Document

## Original Problem Statement
Enterprise-grade PMS (Property Management System) for hotel operations with channel manager integration (Exely SOAP, HotelRunner REST), runtime enforcement, and operational observability.

## Architecture
- **Backend:** FastAPI + MongoDB (Motor async)
- **Frontend:** React + Shadcn/UI + Tailwind
- **Providers:** Exely (SOAP), HotelRunner (REST)
- **Auth:** JWT-based (demo@hotel.com / demo123)

## Completed Phases

### P1–P3: Foundation
- Core PMS modules (rooms, reservations, folios, night audit)
- Channel manager integration (Exely, HotelRunner)
- Delta/Debounce coalescing engine
- Provider simulation & resilience testing
- 242 passing tests

### P4: Runtime Enforcement (COMPLETED)
- **Hard Fail Gate** — Blocks outbound pushes if critical mappings incomplete
- **Auto-Heal Service** — Conservative auto-healing with whitelist, evidence, escalation
- **Push Loop Worker** — Observable runtime delta-push loop with metrics
- **API:** `/api/lockdown/runtime/` control/status endpoints
- **Tests:** 47 new tests, all passing

### P5: Dashboard Notifications, Runtime Cockpit & Quarantine (COMPLETED — 2026-03-17)
- **Notification Events Service** — 10 event types with severity model:
  - Severity: INFO / WARNING / CRITICAL / BLOCKER
  - Cooldown/deduplication: state-change-only for READY transitions, 5–10min cooldown for spikes
  - Events: tenant_ready/not_ready, mapping_complete/broken, hard_fail_cleared/spike, auto_heal_success/failure_spike, first_verify/verify_failure_spike
  - Slack dispatch for CRITICAL/BLOCKER events
- **Runtime Cockpit** — Unified operational dashboard at `/runtime-cockpit`:
  - Health Summary: production readiness, incidents, quarantine count, verify %, push loop status
  - Flow Metrics: queued, coalesced, emitted, dropped, hard_fail_blocked + push loop controls
  - Reliability: verify ratio, verify counts, dead letters, ack latency, cycle duration
  - Drift & Heal: active drifts, auto-heal stats, manual required
  - Quarantine Visibility: total, classification breakdown, age buckets (< 5min, 5-30min, 30-120min, > 2h), provider breakdown
  - Recent Events: severity counts + event list with timestamps
  - Hard Fail Gate: active blocks, open incidents, 24h stats
- **Quarantine Visibility Service:**
  - Classification: unmapped, ambiguous, provider_error, validation_failed
  - Age buckets: < 5 min, 5–30 min, 30–120 min, > 2 hours
  - Safe Release Guard: validates mapping is fixed + staleness check before quarantine release
- **API Endpoints:**
  - `GET /api/lockdown/runtime/cockpit` — unified metrics
  - `GET /api/lockdown/notifications/events|summary|config`
  - `POST /api/lockdown/notifications/evaluate`
  - `GET /api/lockdown/runtime/quarantine/overview`
  - `POST /api/lockdown/runtime/quarantine/check-release|safe-release`
- **Tests:** 26 new tests (mocked service tests + httpx API tests), all passing
- **Total system tests: 73 (P4: 47 + P5: 26)**

## Current Test Status
| Suite | Tests | Status |
|-------|-------|--------|
| P4 Runtime Enforcement | 47 | PASS |
| P5 Cockpit & Notifications | 26 | PASS |
| **Total** | **73** | **ALL PASS** |

## Prioritized Backlog

### P1 — Next
- **Narrow Rollout Framework** — Controlled live simulation (1 tenant, 1 hotel, 2 providers, 7 days)
- **Auto-Heal Intelligence** — Confidence score, provider-specific heal rules, historical success rate

### P2 — Soon
- **Operator Panel Upgrade** — Severity (low/medium/high/blocking) + playbook suggestions per incident
- **High-Signal Slack Notifications** — Refined strategy, key events only

### P3 — Backlog
- Deprecated file cleanup (hotelrunner.py, client.py, exely_client_legacy.py)
- Core Lockdown Block B & C (ProviderCapabilityMatrix, Reconciliation Truth Table)
- Financial Module Hardening (Folio, Night Audit)
- Tenant Management (per-tenant rollout gates, feature flags)

## Key Files
| Area | File |
|------|------|
| Notification Events | `/app/backend/domains/channel_manager/notification_events_service.py` |
| Notification Router | `/app/backend/domains/channel_manager/notification_events_router.py` |
| Quarantine Service | `/app/backend/domains/channel_manager/quarantine_service.py` |
| Runtime Router | `/app/backend/domains/channel_manager/runtime_enforcement_router.py` |
| Hard Fail Gate | `/app/backend/domains/channel_manager/ari/hard_fail_gate.py` |
| Auto-Heal Service | `/app/backend/domains/channel_manager/auto_heal_service.py` |
| Push Loop Worker | `/app/backend/domains/channel_manager/ari/push_loop_worker.py` |
| Runtime Cockpit UI | `/app/frontend/src/pages/RuntimeCockpitPage.jsx` |
| P5 Tests | `/app/backend/tests/test_p5_cockpit_notifications.py` |
| P4 Tests | `/app/backend/tests/test_p4_runtime_enforcement.py` |

## Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
