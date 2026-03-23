# Syroce PMS — Product Requirements Document

## Original Problem Statement
Enterprise-grade hotel management platform (PMS) with multi-tenant architecture, channel management, CI/CD observability, and operational intelligence capabilities.

## Core Architecture
- **Backend**: FastAPI + MongoDB (motor async) + Redis
- **Frontend**: React (Vite) + Recharts + Shadcn/UI
- **CI/CD**: GitHub Actions with standardized notifications and smoke tests
- **Multi-tenant**: Organization-based tenant isolation

## User Personas
| Role | Access |
|------|--------|
| super_admin | Full system access, Control Plane, Ops |
| property_manager | Property-level operations |
| front_desk | Booking, check-in/out |
| guest | Self-service portal |

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

---

## Completed Features

### Phase A: Core PMS
- Multi-tenant auth (JWT)
- Room management with room types
- Booking engine with availability checks
- Guest management
- Rate plans and pricing

### Phase B: Channel Manager
- Provider connectors (Exely, HotelRunner)
- Inventory sync service
- Rate sync service
- Reservation import
- Reconciliation service

### Phase C: Room Night Locks & Inventory
- C.1: `room_type_inventory` materialized view from `room_night_locks`
- Accounts for: booking, hold, OOO, OOS locks
- Sellable formula: `total - locked_booking - locked_hold - locked_ooo - locked_oos`
- Auto-reconciliation every 5 minutes

### Phase D: CI/CD Observability (P0 — COMPLETE)
- Standardized GitHub Actions workflows (ci-cd.yml, deploy.yml)
- Rich notifications with GitHub annotations + job summaries
- Consistent smoke tests (4 key endpoints, formatted table)
- Deploy event tracking + deploy trend endpoint
- Deploy Dashboard with Recharts trend chart

### Phase E: Inventory Ledger Alignment (P0 — COMPLETE, 2026-03-23)
**Critical change**: Channel manager's `_detect_inventory_deltas()` now reads exclusively from `room_type_inventory` materialized view.
- **Old**: Computed availability from `db.rooms` count - `db.bookings` count (missed holds, OOO, OOS)
- **New**: Reads `sellable` from `room_type_inventory` (authoritative, lock-aware)
- **No fallback**: If view is stale → reconcile first, never fall back to old computation
- **Freshness check**: fresh (<5min), recent (<15min), stale (>15min), empty
- **Stale behavior**: Deterministic — triggers reconciliation, reports degraded status
- **Source tagging**: All availability changes tagged with `source: "room_type_inventory"`

### Phase F: DORA Metrics (COMPLETE, 2026-03-23)
- 4 DORA metrics: deployment_frequency, change_failure_rate, MTTR, lead_time
- Rating system: elite/high/medium/low/no_data
- Daily trend breakdown
- **Correlation layer**: DORA × Channel Health cross-reference
  - deploy frequency vs drift events
  - change failure rate vs sync success
  - MTTR vs import failures
- Time window, tenant, and provider filters

### Phase G: Unified Ops View (COMPLETE, 2026-03-23)
**Decision console** (not just dashboard) — single screen for operational intelligence:
- Inventory Alignment block (status, drift count, provider breakdown)
- Deploy Health block (per-environment success rates)
- DORA Metrics block (4 metrics + mini trend chart)
- Provider Health block (per-provider drift status)
- Correlation block (DORA × Channel Health inferences)
- Reconciliation Queue block (freshness, room-type-night count)
- Drill-down from each block to detailed views
- Auto-refresh every 60 seconds

---

## API Endpoints

### Control Plane / Ops
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/ops/deploys | Record deploy event |
| GET | /api/ops/dashboard/deploys | Deploy history |
| GET | /api/ops/dashboard/deploy-stats | Deploy statistics |
| GET | /api/ops/dashboard/deploy-trend | Daily deploy trend |
| GET | /api/ops/dashboard/inventory-alignment | Inventory ledger alignment status |
| GET | /api/ops/dashboard/dora-metrics | DORA release metrics |
| GET | /api/ops/dashboard/dora-correlation | DORA × Channel Health correlation |
| GET | /api/ops/dashboard/channel-health | Channel health dashboard |
| GET | /api/ops/dashboard/tech-debt | Tech debt tracking |

---

## Key DB Collections

### deploy_events
```json
{
  "sha": "string",
  "environment": "string",
  "status": "string",
  "triggered_by": "string",
  "started_at": "datetime",
  "finished_at": "datetime",
  "duration_seconds": "float",
  "commit_message": "string",
  "rollback_of": "string | null"
}
```

### room_type_inventory (materialized view)
```json
{
  "tenant_id": "string",
  "date": "string (YYYY-MM-DD)",
  "room_type": "string",
  "total": "int",
  "locked_booking": "int",
  "locked_hold": "int",
  "locked_ooo": "int",
  "locked_oos": "int",
  "sellable": "int",
  "last_computed_at": "datetime ISO"
}
```

---

## Prioritized Backlog

### P1 — Next
- **Sandbox Testing**: Exely/HotelRunner real-world simulation
- **SEC-001**: Secrets Management Rollout
- **SEC-002**: Crypto Migration

### P2 — Future
- Enable Strict Tenant Mode (`STRICT_TENANT_MODE=true`)
- Migrate `motor` → `pymongo` native async
- Production build with `vite build` + Nginx static serving
- Quarantine burn-down (engineering hygiene)

### P3 — Vision
- Unified "Channel Health + Deploy + KPI" dashboard (extended version)
- Real-time alerting on drift detection
- Automated rollback on drift threshold
