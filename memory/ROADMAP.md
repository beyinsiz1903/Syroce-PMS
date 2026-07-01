# Syroce PMS — ROADMAP

## Completed (March 2026)

### Phase A-I: Foundation
- [x] All core modules (Notification, Auto-Action, Unified Ops, Control Plane, Channel Health, Drift, Import Bridge, Outbox, ARI, Crypto/Secrets)

### Decision-Driven UX
- [x] Dashboard Command Center, Room Board, Front Desk, Payment Dialog, Reservation Ops Panel

### P0 Bug Fixes
- [x] HMR page auto-refresh permanent fix (3-layer defense + feature flag + compat check)

### P1 Sprint
- [x] Sandbox Simulation — 5 resilience scenarios, 2 providers, 10/10 pass rate
- [x] SEC-001 Secrets Management Rollout — rotation plan, rollback, tenant/provider scoping, access audit
- [x] SEC-002 Crypto Migration Rollout — dual-read/write status, cutover metrics, key versioning, fallback
- [x] Sandbox Dashboard Visualization — provider cards, trend chart, regression alerts, correlation
- [x] /api/ops/* Admin Guard — role-based access control
- [x] Alert -> Business KPI Correlation — severity, runbook links, tenant/provider/property context

### P2 Sprint (Current)
- [x] CI/CD Pipeline Sandbox Integration — 3-tier deploy validation (PR Gate, Staging Gate, Nightly Resilience)
  - Acceptance criteria: oversell=0, duplicate=0, inconsistent state=0, stale recovery, reconciliation
  - Deploy gate verdict: PASS/BLOCK/WARN
  - Separate health badges: sandbox_validation / staging_deploy_validation / prod_health
  - Runbook per failure with severity, impact, rollback
  - Results persisted to dashboard with build_id, commit_sha, deploy_id

## P2 — Remaining
- [ ] Wire failure tracking into import bridge, outbox worker, ARI push engine
- [ ] Enable Strict Tenant Mode
- [ ] Legacy DB import migration (~264 imports)
- [ ] pms.py decomposition (2714 lines -> modular services)
- [ ] Legacy collection cleanup (~489 collections)
- [ ] Load and chaos testing

## P3 — Future
- [ ] Vite production build + Nginx
- [ ] Go-live runbook, SLO/SLA documentation, incident playbooks
- [ ] AWS KMS / HashiCorp Vault integration
- [ ] PII masking and stress testing
- [ ] Motor -> pymongo async migration
- [ ] HMR guard decommission
- [ ] Configure Slack webhook for production alerts
