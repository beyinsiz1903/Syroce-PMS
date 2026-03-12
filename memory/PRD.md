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
#### 7.1 Real WebSocket Push Connections
- Authenticated WebSocket sessions with JWT validation
- Tenant-aware channel subscription and role-based event filtering
- Heartbeat/keepalive mechanism (30s interval)
- Event replay buffer for missed messages on reconnect
- Live front desk queue, housekeeping board, audit exception feed
- VIP arrival alerts, overbooking risk detection
- Files: `websocket_hub.py`, router at `/api/enterprise/ws/*`

#### 7.2 Third-Party Messaging Gateway
- Provider abstraction: Twilio (SMS), SendGrid (Email), WhatsApp
- All providers in MOCK mode (activate with API keys)
- Template-based messaging with variable rendering
- Delivery tracking with full lifecycle (pending → delivered/failed)
- Failed delivery retry with exponential backoff (3 retries)
- Consent/opt-in model per guest per channel
- Per-tenant per-channel rate limiting (60/min, 500/hr)
- Provider health monitoring
- Messaging analytics (delivery rates by channel)
- Files: `messaging_gateway.py`, router at `/api/enterprise/messaging/*`

#### 7.3 Revenue Auto-Pricing Workflow
- Recommendation creation (manual or ML-sourced)
- Approval workflow: approve → apply → push to channels
- Rejection workflow with reason tracking
- Full rollback support (restores original room prices)
- Protected dates / blackout rules (no auto-pricing)
- Automation policy: full_auto / supervised / manual
- Max auto-change percentage thresholds
- Channel push status tracking
- Pricing audit trail for all actions
- Files: `revenue_autopricing.py`, router at `/api/enterprise/autopricing/*`

#### 7.4 Cross-Module Deep Integration Bus
10 operational intelligence pathways:
1. Cancellation prediction → overbooking strategy
2. Booking probability → revenue recommendation confidence
3. Comp set price gap → ADR recommendation
4. Guest request volume → housekeeping priority
5. VIP arrival → room readiness priority
6. Night audit exception → escalation queue
7. Failed messaging → guest journey fallback
8. Sync failure → operations alert
9. Revenue auto-apply result → dashboard metrics
10. Reservation risk signals → front desk warning badges
- Files: `cross_module_bus.py`, router at `/api/enterprise/integration/*`

---

## Architecture

```
/app
├── backend/
│   ├── modules/platform_scaling/
│   │   ├── websocket_hub.py          # WebSocket connection manager
│   │   ├── messaging_gateway.py       # Twilio/SendGrid/WhatsApp abstraction
│   │   ├── revenue_autopricing.py     # Auto-pricing workflow
│   │   ├── cross_module_bus.py        # Cross-module integration bus
│   │   ├── event_architecture.py      # Event architecture (Phase 6)
│   │   ├── multi_property_platform.py # Multi-property (Phase 6)
│   │   ├── revenue_ml.py             # Revenue ML (Phase 6)
│   │   └── competitive_analysis.py    # Comp set analysis (Phase 6)
│   ├── routers/
│   │   ├── enterprise_live.py         # Enterprise Live router
│   │   └── platform_scaling.py        # Platform Scaling router
│   ├── tests/
│   │   ├── test_enterprise_features.py # 38 tests
│   │   └── test_platform_scaling.py    # 28 tests
│   └── server.py
├── frontend/src/
│   ├── pages/
│   │   ├── EnterpriseLiveDashboard.js # Enterprise Live Dashboard
│   │   └── PlatformScalingDashboard.js
│   ├── config/navItems.js
│   └── App.js
└── memory/PRD.md
```

## API Endpoints

### Enterprise Live APIs
| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/api/enterprise/ws/live` | Authenticated WebSocket |
| GET | `/api/enterprise/ws/stats` | Connection stats |
| GET | `/api/enterprise/ws/live-data` | Live operational data |
| POST | `/api/enterprise/messaging/send` | Send message |
| POST | `/api/enterprise/messaging/templates` | Create template |
| GET | `/api/enterprise/messaging/templates` | List templates |
| GET | `/api/enterprise/messaging/history` | Delivery history |
| POST | `/api/enterprise/messaging/consent` | Update consent |
| GET | `/api/enterprise/messaging/provider-health` | Provider status |
| GET | `/api/enterprise/messaging/analytics` | Analytics |
| POST | `/api/enterprise/autopricing/recommendation` | Create recommendation |
| POST | `/api/enterprise/autopricing/approve` | Approve & apply |
| POST | `/api/enterprise/autopricing/reject` | Reject |
| POST | `/api/enterprise/autopricing/rollback` | Rollback |
| GET | `/api/enterprise/autopricing/dashboard` | Dashboard |
| POST | `/api/enterprise/autopricing/policy` | Set automation policy |
| POST | `/api/enterprise/autopricing/protected-dates` | Add blackout dates |
| POST | `/api/enterprise/integration/run-all` | Run all integrations |

## Testing
- Backend: 38 pytest tests (100% pass) at `tests/test_enterprise_features.py`
- E2E: Testing agent validation (100% backend + frontend)
- Test reports: `/app/test_reports/iteration_36.json`

## Mocked Components
- Twilio SMS provider (mock mode - no TWILIO_ACCOUNT_SID)
- SendGrid Email provider (mock mode - no SENDGRID_API_KEY)
- WhatsApp provider (mock mode - no WHATSAPP_API_KEY)

## Upcoming Tasks (P1)
- Activate live Twilio/SendGrid/WhatsApp with real API keys
- Connect Revenue ML models to auto-pricing pipeline
- Real-time WebSocket push for cross-module events
- Training pipelines for ML models

## Backlog (P2-P3)
- Granular user permissions for multi-property
- Advanced reporting and analytics
- Mobile app for staff notifications
- Production monitoring and alerting
