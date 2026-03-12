# Hotel Operating System - PRD

## Original Problem Statement
Enterprise-grade Hotel Operating System - transition from system of record to data-driven automated decision support system. The platform covers PMS Core, Channel/Distribution, Operations, Intelligence, Guest Experience, and Platform Scale.

## Core Architecture
- **Backend**: FastAPI + MongoDB (motor async) + Python 3.11
- **Frontend**: React + Shadcn/UI + Tailwind CSS
- **Auth**: JWT-based, RBAC, tenant isolation
- **Language**: Turkish UI

## Implemented Modules

### Phase 1-4 (Previous)
- PMS Core (reservations, front desk, folio/billing, housekeeping, night audit, RBAC)
- Channel/Distribution (connector-first, inventory sync, reservation import, rate push)
- Operations (real-time events, alerting, reliability monitoring, scheduler, audit trail)
- Intelligence (revenue management, revenue ML pipeline, competitive set, operational AI, guest intelligence)
- Guest Experience (journey layer, online check-in, requests, messaging gateway, review capture)
- Platform Scale (multi-property, central revenue, global alerts, cross-module orchestration)

### Phase 5: Data Intelligence (Previous Fork)
- Revenue ML Pipeline (mock data)
- Operational AI (mock data)
- Guest Intelligence (mock data)
- DataIntelligenceDashboard (3-tab UI)

### Phase 6: Platform Intelligence & Automation (Current Fork - March 12, 2026)

#### 6A. Real Messaging Activation
- **Module**: `/backend/modules/messaging/` (providers.py, service.py, models.py)
- **Router**: `/backend/routers/messaging.py` (prefix: `/api/messaging-center`)
- **Frontend**: `/frontend/src/pages/MessagingDashboard.js`
- Twilio SMS, SendGrid Email, WhatsApp provider implementations (real HTTP clients)
- Tenant-specific provider credentials
- Template-based sending with variable rendering
- Delivery status tracking with retry support
- Consent/opt-in enforcement
- Rate limiting per provider
- Provider health monitoring
- Fallback strategy (WhatsApp → SMS → Email)
- Message audit trail + delivery metrics

#### 6B. ML Model Scheduled Execution
- **Module**: `/backend/modules/ml_scheduler/service.py`
- **Router**: `/backend/routers/ml_scheduler.py` (prefix: `/api/data-intelligence/schedules`)
- **Frontend**: `/frontend/src/pages/MLSchedulerDashboard.js`
- Cron-based execution scheduling per model type
- Revenue ML: 6h, Operational AI: 1h, Guest Intelligence: 24h
- Duplicate run prevention
- Execution status lifecycle (pending → running → completed/failed)
- Failure retry with backoff
- Stale model output detection
- Model version tracking + snapshot retention
- Alert integration for failed/low-confidence runs

#### 6C. Revenue Autopilot Mode
- **Module**: `/backend/modules/revenue_autopilot/service.py`
- **Router**: `/backend/routers/revenue_autopilot_v2.py` (prefix: `/api/revenue-autopilot`)
- **Frontend**: `/frontend/src/pages/RevenueAutopilotDashboard.js`
- Three modes: Full Auto, Supervised, Advisory
- Confidence threshold rules (auto-apply ≥85%, queue ≥50%)
- Max price change percentage limits
- Blackout date and protected room type handling
- Approval queue with approve/reject/rollback
- Channel push confirmation tracking
- Daily autopilot summary
- Human override logging + complete audit trail

#### 6D. WebSocket/PubSub Event Broadcast
- **Module**: `/backend/modules/event_broadcast/service.py`
- **Router**: `/backend/routers/websocket_health.py` (prefix: `/api/websocket`)
- Tenant-aware channel routing
- Role-based event filtering (admin=all, front_desk, housekeeping, etc.)
- Session presence tracking
- Missed event replay support
- Event throughput monitoring

#### 6E. Advanced Reporting & Analytics Export
- **Module**: `/backend/modules/analytics_export/service.py`
- **Router**: `/backend/routers/analytics_export.py` (prefix: `/api/reports/export`)
- **Frontend**: `/frontend/src/pages/AnalyticsExportDashboard.js`
- 8 report types: revenue ML, operational AI, guest intelligence, messaging, autopilot, audit, property comparison, management summary
- CSV and JSON export formats
- Date range and property filters
- Export job history

#### 6F. Cross-Module Enrichment
- **Module**: `/backend/modules/cross_enrichment/service.py`
- Revenue apply → rate push tracking
- Revenue failure → operations alert
- Guest churn → messaging campaign
- VIP arrival → room readiness priority
- Sentiment drop → service recovery alert
- Operational density → staffing recommendation
- Messaging failure → fallback tracking
- Stale snapshot → admin warning
- Multi-property summary → autopilot + AI health

## Data Models (MongoDB Collections)
- `messaging_provider_configs` - Provider credentials and health
- `messaging_delivery_logs` - Delivery tracking
- `messaging_templates` - Message templates
- `messaging_consents` - Opt-in/out tracking
- `ml_schedule_policies` - Scheduler configuration
- `ml_execution_jobs` - Execution history
- `ml_snapshots` - Model output snapshots
- `revenue_autopilot_policies` - Autopilot configuration
- `revenue_approval_queue` - Price change approvals
- `revenue_apply_results` - Applied price changes
- `analytics_export_jobs` - Export job tracking
- `event_broadcast_log` - Event history
- `system_alerts` - Cross-module alerts
- `cross_enrichment_log` - Enrichment event tracking
- `rate_push_tracking` - Channel rate push tracking
- `messaging_campaign_candidates` - Campaign targets
- `room_readiness_priority` - VIP room priority

## Testing
- `/backend/tests/test_platform_v2.py` - 33 tests (100% pass)
- `/backend/tests/test_data_intelligence.py` - 25 tests (previous)
- E2E testing via testing_agent (iteration_38.json - 100% success)

## API Endpoints

### Messaging Center (/api/messaging-center)
- GET/POST /providers, PUT /providers/{id}, POST /providers/health-check
- GET/POST /templates, PUT /templates/{id}
- POST /send, POST /retry/{id}
- GET /delivery-logs, GET /metrics, POST /consent

### ML Scheduler (/api/data-intelligence/schedules)
- GET /dashboard, GET /policies, PUT /policies/{model_type}
- POST /trigger, GET /history, GET /stale

### Revenue Autopilot (/api/revenue-autopilot)
- GET /dashboard, GET/PUT /policy
- GET /queue, POST /process
- POST /queue/{id}/approve, POST /queue/{id}/reject, POST /queue/{id}/rollback
- GET /summary

### WebSocket Health (/api/websocket)
- GET /health, POST /sessions/register, DELETE /sessions/{id}
- POST /publish, GET /replay

### Analytics Export (/api/reports/export)
- GET /available, POST /generate, POST /download, GET /history

## Backlog (P1-P3)
- P1: Replace mock ML models with real data pipelines
- P1: Real Redis Pub/Sub integration (currently in-memory)
- P2: Scheduled report generation (cron-based)
- P2: PDF export format
- P3: Multi-property comparison analytics
- P3: Real-time WebSocket push to frontend
