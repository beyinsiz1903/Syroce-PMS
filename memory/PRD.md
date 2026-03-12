# Hotel Operating System - Enterprise SaaS Platform PRD

## Original Problem Statement
Build an enterprise-grade hotel operating system (PMS) as a true SaaS platform with modular architecture supporting multi-property management, real-time operations, revenue intelligence, and third-party integrations.

## User Persona
- **Primary**: Principal Hospitality Software Architect overseeing enterprise hotel operations
- **Language**: Turkish
- **Auth**: demo@hotel.com / demo123

---

## Implemented Modules

### PHASE 1 - PMS Core (DONE)
- Reservation state machine, front desk workflow, folio/billing
- Housekeeping, night audit, RBAC, PMS dashboard

### PHASE 2 - Channel Distribution (DONE)
- Connector-first architecture, inventory sync, reservation import
- Provider contract hardening, mapping readiness, rate push tracking

### PHASE 3 - Operations (DONE)
- Real-time event architecture, alerting engine, reliability monitoring
- Connector health dashboard, readiness checklist, scheduler worker, audit trail

### PHASE 4 - Intelligence (DONE)
- Revenue management engine, Revenue ML, comp set analysis

### PHASE 5 - Guest Experience (DONE)
- Guest journey layer, online check-in, guest requests, review capture

### PHASE 6 - Platform Scale (DONE)
- Multi-property platform, central revenue management, global alerts

### PHASE 7 - Enterprise Live Operations (DONE - 2026-03-12)
- Real WebSocket Push, Messaging Gateway, Auto-Pricing Workflow, Cross-Module Bus

### PHASE 8 - Data-Driven Intelligence (DONE - 2026-03-12)

#### 8.1 Revenue ML Pipeline
- Full ML pipeline: demand forecast → rate elasticity → booking probability → cancellation prediction → ADR recommendation
- Confidence scoring (0.1-0.95 range) with high/medium/low bands
- Human override threshold at 0.60 (below requires manual approval)
- Explainability: demand_signal, pace_signal, cancellation_risk, price_sensitivity, recommendation_reason
- Auto-apply eligibility based on confidence + change percentage
- Integration with existing revenue_autopricing workflow
- Pipeline execution with persistent snapshots in revenue_ml_snapshots
- Model execution logging in model_execution_logs
- Files: `modules/data_intelligence/revenue_ml_pipeline.py`

#### 8.2 Operational AI
- Check-in load prediction (hourly forecast, peak hour, arrival pressure score)
- Housekeeping workload prediction (departures, stayovers, arrivals, total hours)
- Room readiness ETA prediction (per-room ETA with priority for arrival rooms)
- Maintenance failure risk scoring (frequency, recency, priority escalation factors)
- Staffing recommendations (front desk + housekeeping, combined pressure score)
- Workload heatmap (floor-based HK, hourly check-in distribution)
- Persistent snapshots in operational_ai_snapshots
- Files: `modules/data_intelligence/operational_ai.py`

#### 8.3 Guest Intelligence
- Guest lifetime value (revenue, ancillary, frequency, projected annual, value score 0-100)
- Guest segmentation (6 types: loyal_high_value, business_regular, leisure_regular, high_spender, first_timer, occasional)
- Churn prediction (recency, cancellation ratio, declining frequency, complaints)
- Upsell recommendations (room upgrade, F&B, spa, late checkout, early checkin)
- Value distribution (platinum/gold/silver/bronze tiers)
- Explainability: stay_frequency, average_spend, recent_sentiment, request_volume, cancellation_history
- Persistent snapshots in guest_intelligence_snapshots
- Files: `modules/data_intelligence/guest_intelligence.py`

#### 8.4 Data Intelligence Dashboard (Frontend)
- 3-tab layout: Revenue Intelligence, Operational AI, Guest Intelligence
- Revenue: forecast chart, summary cards, pipeline runner, recommendation cards with explainability
- Operational: check-in hourly chart, HK workload breakdown, staffing recommendations, maintenance risk table
- Guest: value distribution, segment breakdown, churn risk table, upsell opportunities
- Files: `frontend/src/pages/DataIntelligenceDashboard.js`

---

## Architecture

```
/app
├── backend/
│   ├── modules/
│   │   ├── data_intelligence/               # (PHASE 8 - NEW)
│   │   │   ├── revenue_ml_pipeline.py       # ML → Auto-pricing orchestration
│   │   │   ├── operational_ai.py            # Operational prediction models
│   │   │   └── guest_intelligence.py        # Guest analytics models
│   │   └── platform_scaling/
│   │       ├── websocket_hub.py
│   │       ├── messaging_gateway.py
│   │       ├── revenue_autopricing.py
│   │       ├── cross_module_bus.py
│   │       ├── revenue_ml.py               # Base ML models (Phase 4)
│   │       └── ...
│   ├── routers/
│   │   ├── data_intelligence.py             # (PHASE 8 - NEW, 15 endpoints)
│   │   ├── enterprise_live.py
│   │   └── platform_scaling.py
│   ├── tests/
│   │   ├── test_data_intelligence.py        # (PHASE 8 - NEW, 25 tests)
│   │   └── test_enterprise_features.py
│   └── server.py
├── frontend/src/
│   ├── pages/
│   │   ├── DataIntelligenceDashboard.js     # (PHASE 8 - NEW)
│   │   ├── EnterpriseLiveDashboard.js
│   │   └── PlatformScalingDashboard.js
│   ├── config/navItems.js
│   └── App.js
└── memory/PRD.md
```

## API Endpoints

### Data Intelligence APIs (Phase 8)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/data-intelligence/revenue/run-pipeline` | Execute full ML pipeline |
| GET | `/api/data-intelligence/revenue/forecast-dashboard` | Revenue forecast dashboard |
| GET | `/api/data-intelligence/revenue/recommendations` | ML pricing recommendations |
| GET | `/api/data-intelligence/operations/dashboard` | Operational AI dashboard |
| GET | `/api/data-intelligence/operations/staffing` | Staffing recommendations |
| GET | `/api/data-intelligence/operations/workload-heatmap` | Workload heatmap |
| GET | `/api/data-intelligence/operations/room-readiness` | Room readiness ETA |
| GET | `/api/data-intelligence/operations/maintenance-risk` | Maintenance failure risk |
| GET | `/api/data-intelligence/guests/dashboard` | Guest intelligence dashboard |
| GET | `/api/data-intelligence/guests/{id}/summary` | Single guest intelligence |
| GET | `/api/data-intelligence/guests/{id}/churn-risk` | Guest churn prediction |
| GET | `/api/data-intelligence/guests/{id}/upsell` | Guest upsell recommendations |
| GET | `/api/data-intelligence/guests/segments` | Segment distribution |
| GET | `/api/data-intelligence/guests/churn-summary` | Churn risk summary |
| GET | `/api/data-intelligence/guests/upsell-opportunities` | Upsell opportunities |

## Data Collections (Phase 8)
- `revenue_ml_snapshots` - Pipeline execution results
- `operational_ai_snapshots` - Operational AI predictions
- `guest_intelligence_snapshots` - Guest analytics results
- `model_execution_logs` - Model run audit logs

## Testing
- Backend: 25 pytest tests (100% pass) at `tests/test_data_intelligence.py`
- E2E: Testing agent validation (100% backend + frontend) - iteration_37
- Test reports: `/app/test_reports/iteration_37.json`

## Mocked Components
- Twilio SMS provider (mock mode)
- SendGrid Email provider (mock mode)
- WhatsApp provider (mock mode)

## Upcoming Tasks (P1)
- Activate live Twilio/SendGrid/WhatsApp with real API keys
- Training pipelines for ML models with scheduled execution
- Real-time WebSocket push for data intelligence events

## Backlog (P2-P3)
- Redis Pub/Sub for WebSocket scaling
- Granular user permissions for multi-property
- Advanced reporting and analytics
- Mobile app for staff notifications
- Production monitoring and alerting
