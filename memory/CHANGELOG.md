# CHANGELOG

## [2026-03-23] Notification Layer + Auto-Action + Unified Ops View Redesign

### Notification Routing (Config-Driven)
- **warning** → dashboard only (no external notification)
- **critical** → dashboard + `ALERT_WEBHOOK_URL` (Slack-compatible webhook, no-op if absent)
- **severe** → dashboard + `ALERT_WEBHOOK_URL` + `ESCALATION_WEBHOOK_URL` + auto-action trigger
- Slack Block Kit formatted payload with severity emoji, provider details, runbook link

### Auto-Action Engine
- **New**: `/app/backend/controlplane/auto_actions.py`
- Severe drift → triggers existing `ReconciliationEngine.reconcile()` with `trigger_source=auto_action` metadata
- Guardrails: 15-min cooldown per tenant, eligibility check, single execution per provider/tenant, timeline logging
- Failed auto-action fires new alert via `AlertingEngine`
- Full audit trail in `cp_auto_actions` collection + `event_timeline`
- **Endpoints**: `GET /api/ops/dashboard/auto-actions`, `GET /api/ops/dashboard/ops-kpis`

### Unified Ops View Redesign — "Urunun Kalbi"
- **Top Row**: Channel Health (alignment, freshness, providers) + Deploy Health (env success rates)
- **Middle**: Live Drift Alerts (severity badges, auto-heal indicators, acknowledge, runbook links)
- **Bottom**: KPI Dashboard — Sync Success, MTTR, Push SLA, Auto-Heal stats, DORA mini metrics, Drift Trend chart, DORA × Kanal Korelasyonu, summary footer
- Every widget has drill-down support + data-testid attributes

### Testing
- 21/21 backend tests passed (ops-kpis, auto-actions, notification routing, guardrails)
- 10/10 frontend elements verified, all interactions working

---

## [2026-03-23] Drift Threshold Alerting

### Drift Alerting Engine
- **New**: `/app/backend/controlplane/drift_alerting.py` — threshold-based drift alert engine
  - 3 severity tiers: warning (1+ drift/15min), critical (3+ room-night drift/15min), severe (post-recon drift)
  - Alert payload: tenant, providers, drift_count, drift_nights, drift_or_stale, last_reconciliation_result, runbook_link
  - Cooldown-aware firing (15 min cooldown per severity per tenant)
  - Webhook relay via existing AlertingEngine
  - Lifecycle: fire → persist → acknowledge
- **Endpoints**:
  - `GET /api/ops/dashboard/drift-alerts` — list with filters
  - `GET /api/ops/dashboard/drift-alerts/summary` — severity overview
  - `POST /api/ops/dashboard/drift-alerts/evaluate` — evaluate and fire
  - `POST /api/ops/dashboard/drift-alerts/{id}/acknowledge` — acknowledge alert
- **New runbook**: `inventory_drift_detected` — structured resolution for drift incidents
- **Frontend**: `DriftAlertPanel` in UnifiedOpsView — top-priority alert block with severity badges, acknowledge buttons, runbook links

### Testing
- 15/15 backend tests passed (drift_alerting_api)
- All frontend elements verified (DriftAlertPanel, evaluate button, toast notifications)

---

## [2026-03-23] Inventory Ledger Alignment + DORA Metrics + Unified Ops View

### Inventory Ledger Alignment (P0 — CRITICAL)
- **BREAKING CHANGE**: `_detect_inventory_deltas()` in `inventory_sync_service.py` completely rewritten
  - **Removed**: Old `db.rooms` count - `db.bookings` count computation
  - **Added**: Reads exclusively from `room_type_inventory` materialized view
  - **Added**: `_check_inventory_freshness()` method (fresh/recent/stale/empty)
  - **Added**: Stale view → automatic reconciliation trigger (no fallback)
  - **Added**: Source tagging on all availability changes (`source: "room_type_inventory"`)
- **New**: `/app/backend/controlplane/inventory_alignment.py` — alignment computation service
  - Returns: `alignment_status`, `drift_count`, `drift_nights`, `provider_breakdown`
  - Writes drift events to `event_timeline` for auditability
- **Endpoint**: `GET /api/ops/dashboard/inventory-alignment`

### DORA Metrics
- **New**: `/app/backend/controlplane/dora_metrics.py` — DORA metrics + correlation service
  - 4 metrics: deployment_frequency, change_failure_rate, MTTR, lead_time
  - Rating system: elite/high/medium/low/no_data
  - Correlation layer: DORA × Channel Health cross-reference
- **Endpoints**: `GET /api/ops/dashboard/dora-metrics`, `GET /api/ops/dashboard/dora-correlation`

### Unified Ops View (Frontend)
- **New**: `/app/frontend/src/components/UnifiedOpsView.jsx` — decision console
  - 6 blocks: Alignment, Deploy Health, DORA, Provider Health, Correlation, Recon Queue
  - Drill-down from each block, auto-refresh 60s
- **Modified**: `/app/frontend/src/pages/ControlPlane.jsx` — "Ops Merkezi" tab (default)

### Testing
- 30/30 backend tests passed (12 inventory_ledger_alignment + 18 ops_dashboard)
- 16/16 frontend elements verified
- Regression test: confirms no fallback to booking-based computation

### CI/CD Fix
- Removed duplicate `VITE_BACKEND_URL` from `backend-test` env block in `ci-cd.yml`

---

## [Previous Sessions] — CI/CD Hardening & Control Plane (P0 Complete)
- Standardized CI/CD notifications with GitHub annotations and job summaries
- Added deploy trend endpoint and Recharts visualization
- Fixed `booking_availability` import path in `analytics_router.py`

> **Note:** Historical references to `REACT_APP_BACKEND_URL` in older entries reflect the pre-Vite era.
