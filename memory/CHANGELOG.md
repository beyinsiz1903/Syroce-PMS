# CHANGELOG

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
