# RoomOps PMS — Product Requirements Document

## Original Problem Statement
Build a production-grade **Cross-Provider Reconciliation Engine** and **Operational Channel Monitoring & Alerting System** for a hotel PMS platform (Syroce PMS). The system detects and manages data inconsistencies between a local PMS and two external channel managers: HotelRunner (REST) and Exely (SOAP).

## Architecture Overview
```
/app
├── backend/
│   ├── domains/
│   │   ├── channel_manager/
│   │   │   ├── credential_vault.py          # Encrypted secret storage
│   │   │   ├── provider_config_router.py     # Provider config & validation API
│   │   │   ├── providers/hotelrunner.py      # HotelRunner REST client
│   │   │   ├── providers/exely/              # Exely SOAP client
│   │   │   ├── ingest/                       # Reservation ingest pipeline
│   │   │   ├── ari/                          # ARI push engine
│   │   │   ├── reconciliation_engine/        # Reconciliation engine
│   │   │   ├── monitoring/
│   │   │   │   ├── monitoring_router.py      # Monitoring + Slack + Trends API
│   │   │   │   ├── alert_dispatch.py         # Slack webhook dispatch
│   │   │   │   ├── alert_engine.py           # Alert evaluation
│   │   │   │   ├── aggregator.py             # Metrics aggregation
│   │   │   │   └── monitoring_worker.py      # Background worker + metrics history
│   │   │   └── ...
│   ├── GO_LIVE_PLAYBOOK.md                   # Production go-live checklist
│   └── ...
├── frontend/src/
│   ├── pages/DataModelDashboard.jsx          # Main dashboard with all tabs
│   ├── components/TrendCharts.jsx            # 24h trend charts component
│   └── ...
```

## Completed Features

### PMS Core — Completed
- Reservation core, Night audit, Frontdesk operations

### Channel Manager Core — Completed
- Provider integrations (HotelRunner REST + Exely SOAP)
- Reservation ingest pipeline
- ARI push engine
- Drift detection

### Data Reliability — Completed
- Raw event store, Reservation lineage
- Versioning + payload hash, Replay mechanism

### Reconciliation Engine — Completed
- Cross-provider data comparison
- Case management (open/resolved/acknowledged)
- Snapshot collectors for both providers

### Operational Monitoring & Alerting — Completed
- 5 health domains: Provider, Ingest, ARI, Reconciliation, Queue
- Alert engine with threshold evaluation
- Dashboard with real-time metrics

### Provider Credential Configuration + Validation — Completed (March 2026)
- Encrypted secret storage (credential_vault.py)
- provider_connections + credentials_ref pattern
- Automated validation suite (connection, rooms, rates, reservations)
- Readiness scoring (auth_ok, pull_ok, mapping %, import ready)
- Provider Config tab in dashboard

### Slack Alert Integration — Completed (March 2026)
- Alert Dispatch Service (Dashboard + Slack + future Email)
- Severity-based filtering (critical, high, medium, info)
- Webhook URL configuration via UI
- Test message sending
- Slack config panel in Monitoring tab

### Monitoring Trend Charts — Completed (March 2026)
- Metrics snapshot storage (monitoring_metrics_history collection)
- Time-series API endpoint (GET /trends?hours=N)
- Mini bar charts with trend indicators
- 4 metric panels: Ingest, ARI, Reconciliation, Queue
- Selectable time ranges: 6h, 12h, 24h, 48h

### Pilot Hotel Go-Live Playbook — Completed (March 2026)
- 6-phase production checklist document
- Phase 1: Pre-Go-Live Readiness (T-7)
- Phase 2: Sandbox Validation (T-5)
- Phase 3: Stress Testing (T-3) — 24h soak, burst, ARI storm
- Phase 4: Go-Live Day (T-0) — Checklist + rollback plan
- Phase 5: Post-Go-Live (T+1 → T+7)
- Phase 6: Scaling plan

## Key API Endpoints

### Provider Configuration
- GET /api/channel-manager/config/providers
- POST /api/channel-manager/config/providers/{provider}/credentials
- GET /api/channel-manager/config/providers/{provider}/credentials
- DELETE /api/channel-manager/config/providers/{provider}/credentials
- POST /api/channel-manager/config/providers/{provider}/validate
- POST /api/channel-manager/config/providers/{provider}/test-connection
- GET /api/channel-manager/config/providers/{provider}/readiness

### Monitoring
- GET /api/channel-manager/monitoring/overview
- GET /api/channel-manager/monitoring/alerts
- GET /api/channel-manager/monitoring/metrics
- GET /api/channel-manager/monitoring/providers
- POST /api/channel-manager/monitoring/alerts/{alert_id}/ack
- POST /api/channel-manager/monitoring/alerts/{alert_id}/resolve
- GET /api/channel-manager/monitoring/dispatch-config
- POST /api/channel-manager/monitoring/dispatch-config/slack
- POST /api/channel-manager/monitoring/dispatch-config/slack/test
- GET /api/channel-manager/monitoring/trends

## DB Collections
- provider_secrets: Encrypted credential storage
- alert_dispatch_config: Slack/email dispatch configuration
- monitoring_metrics_history: Time-series metrics snapshots
- monitoring_alerts: Generated alerts
- provider_connections, room_mappings, rate_plan_mappings, etc.

## Pending Tasks

### P0 — Production Credentials
- [ ] Configure real HotelRunner token + hr_id
- [ ] Configure real Exely username + password + hotel_code

### P1 — Real Provider Validation
- [ ] Run full validation with real credentials
- [ ] Verify end-to-end data flow

### P2 — Mapping UI Improvement
- [ ] Enhanced PMS room/rate to provider mapping interface
- [ ] Bulk mapping, auto-suggestions

### P3 — Legacy Collection Cleanup
- [ ] Archive old unused collections
- [ ] Index optimization

### Future
- [ ] Email notification channel
- [ ] Alert notification preferences per user
- [ ] Custom threshold configuration UI
- [ ] Historical metrics archive & long-term trends

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
