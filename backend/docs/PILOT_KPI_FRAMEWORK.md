# Pilot KPI Framework — Market Readiness Measurement

## Status: Draft
## Last Updated: 2026-03

## Context

Technical readiness and market readiness are different disciplines. The Syroce PMS codebase has reached production-candidate maturity (CI/CD hard gates, 391+ passing tests, 0 vulnerabilities, resilience testing). However, market readiness requires live operational evidence from pilot hotel deployments.

This document defines the KPIs that must be measured during pilot onboarding to validate production fitness.

---

## KPI Categories

### 1. Onboarding Efficiency

| KPI | Definition | Target | Measurement Point | Current Status |
|-----|-----------|--------|-------------------|----------------|
| Time to first booking | Hours from deployment to first real reservation processed | < 4 hours | Onboarding checklist completion timestamp | Design (12-step checklist exists) |
| Setup completion rate | % of onboarding steps completed without support intervention | > 80% | `onboarding_progress` collection | Design (auto-detection implemented) |
| Data import duration | Time to import existing reservations, rooms, guests from legacy PMS | < 2 hours (< 500 rooms) | Import bridge logs | Design (import pipeline exists) |
| Staff training time | Hours until front desk can perform check-in/out, booking, folio without help | < 8 hours | Operator feedback | Not yet measured |

### 2. Channel Sync Reliability

| KPI | Definition | Target | Measurement Point | Current Status |
|-----|-----------|--------|-------------------|----------------|
| Ingest success rate | % of inbound webhooks successfully processed to booking | > 99.5% | `event_timeline` pipeline completion | Instrumentable (timeline exists) |
| ARI push success rate | % of outbound ARI updates confirmed by provider | > 99% | `outbox_queue` confirmed vs total | Instrumentable (outbox exists) |
| Sync latency (inbound) | Webhook received to booking created | < 5 seconds (p95) | Timeline stage timestamps | Instrumentable |
| Sync latency (outbound) | Booking change to ARI push confirmed | < 30 seconds (p95) | Outbox enqueue to confirmed timestamp | Instrumentable |
| Duplicate detection rate | % of duplicate webhooks correctly identified and skipped | 100% | Dedup stage in pipeline | Tested (battle tests) |

### 3. Operational Reliability

| KPI | Definition | Target | Measurement Point | Current Status |
|-----|-----------|--------|-------------------|----------------|
| Operator MTTR | Mean time for staff to resolve a front-desk issue (check-in fail, room conflict, etc.) | < 5 minutes | Operator logs / support tickets | Not yet measured |
| Night audit success rate | % of night audit runs completing without manual intervention | > 95% | `night_audit_logs` collection | Design (audit flow exists) |
| Overbooking incidents | Count of double-booked room-nights reaching guest | 0 | `room_night_locks` conflict events | Designed (INV-1 enforced, battle-tested) |
| System uptime | % availability during hotel operating hours (06:00-24:00) | > 99.9% | Health check endpoint monitoring | Instrumentable (health endpoint exists) |
| Control plane alert response | Time from alert to operator acknowledgement | < 15 minutes | `cp_health_snapshots` + operator action log | Design (dashboard exists) |

### 4. Revenue Impact

| KPI | Definition | Target | Measurement Point | Current Status |
|-----|-----------|--------|-------------------|----------------|
| Channel revenue attribution | Revenue from OTA bookings processed through channel manager | Measurable | Folio charges linked to channel bookings | Instrumentable (folio + booking source exists) |
| Rate parity compliance | % of time rates are consistent across channels | > 95% | ARI push logs vs provider rate snapshots | Not yet measured |
| Occupancy improvement | Change in occupancy % after channel manager activation | > 5% lift | Room-night locks vs total room-nights | Instrumentable |
| ADR change | Average Daily Rate trend post-deployment | Neutral or positive | Folio charge aggregation | Instrumentable |

### 5. Support Load

| KPI | Definition | Target | Measurement Point | Current Status |
|-----|-----------|--------|-------------------|----------------|
| Support tickets / week | Number of issues requiring engineering intervention | < 3 after week 2 | External ticket system | Not yet measured |
| Self-service resolution rate | % of issues resolved via control plane / runbooks without escalation | > 70% | Runbook execution logs + operator actions | Design (14 runbooks exist) |
| P0 incidents / month | Critical issues causing booking loss or data corruption | 0 | Incident tracker | Not yet measured |

---

## Measurement Infrastructure Status

| Component | Exists | Live Data | Dashboard |
|-----------|--------|-----------|-----------|
| Event timeline (traceability) | Yes | Yes (dev/test) | Yes (Control Plane) |
| Health dashboard (system health) | Yes | Yes (dev/test) | Yes (Control Plane) |
| Usage metering (API calls, events) | Yes | Yes (dev/test) | Yes (Governance Panel) |
| Onboarding progress tracker | Yes | Yes (dev/test) | Yes (Governance Panel) |
| Folio ledger (revenue tracking) | Yes | Yes (dev/test) | Partial (API only) |
| Outbox monitoring (ARI push) | Yes | Yes (dev/test) | Yes (Control Plane) |
| Room-night lock audit trail | Yes | Yes (dev/test) | Via timeline |
| Operator action logging | Partial | No | No |
| External support ticket integration | No | No | No |
| Rate parity monitoring | No | No | No |

---

## Pilot Graduation Criteria

A pilot hotel graduates from "pilot" to "production customer" when:

1. **Onboarding**: Setup completed in < 1 business day, staff operational in < 3 days
2. **Sync reliability**: Ingest success > 99.5% and ARI push success > 99% over 14 consecutive days
3. **Zero overbookings**: No INV-1 violations during pilot period
4. **Night audit**: > 95% automated success rate over 7 consecutive nights
5. **Support load**: < 3 tickets/week by week 3, trending down
6. **Operator confidence**: Front desk staff rates system > 7/10 in usability survey

---

## Gap: Design vs Live

Most KPIs above are **instrumentable** — the data collection points exist in the codebase — but no pilot hotel has run yet. The transition from "design-level metrics" to "live operational evidence" requires:

1. Deploy to staging with real-ish load (load test suite exists: `/app/load_tests/`)
2. Onboard a pilot hotel (playbook exists: `ONBOARDING_PLAYBOOK.md`)
3. Instrument KPI collection into a monitoring dashboard (partial: Control Plane + Governance Panel)
4. Run for 14+ days and measure against targets above

This is the critical path from technical readiness to market readiness.
