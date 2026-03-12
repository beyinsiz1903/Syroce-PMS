# Hotel Operating System — Enterprise SaaS Platform

## Original Problem Statement
Enterprise hotel operating system platform with PMS core, channel management, revenue ML, operational AI, guest intelligence, messaging, analytics, multi-property support, and production hardening. Goal: Evolve from mock/fallback development mode to production-grade SaaS.

## Architecture
- **Backend**: FastAPI (Python 3.11) on port 8001
- **Frontend**: React 18 with Shadcn UI
- **Database**: MongoDB
- **Event Bus**: Redis Pub/Sub with in-memory fallback
- **Auth**: JWT-based authentication

## Core Modules
### Application Layer (Complete)
- PMS Core (bookings, rooms, guests, folios, invoices)
- Channel Manager (OTA integration, rate distribution)
- Revenue ML / Operational AI / Guest Intelligence
- Messaging Gateway (Twilio SMS, SendGrid Email, WhatsApp)
- Revenue Autopilot (dynamic pricing)
- Analytics Export Center
- Multi-Property Platform

### Platform Hardening Phase 1 (Complete)
- Data Pipeline (feature store, dataset generator, model registry)
- Event Bus Abstraction (Redis Pub/Sub + in-memory fallback)
- Production Observability (metrics, tracing, health)
- Multi-Tenant Security Hardening (tenant scoping, RBAC, vault, masking)

### Production Runtime Phase 2 (Complete — 2026-03-12)
- **Redis Runtime Activation**: Connection manager, health check, reconnect with backoff, env-based mode selection (REDIS_URL), delivery metrics, channel cardinality, backpressure safety
- **Real Messaging Providers**: Twilio SMS, SendGrid Email, WhatsApp with sandbox/test/live modes, credential vault integration, error classification, fallback chain, retry policy, consent enforcement
- **MongoDB Persistence Migration**: All in-memory stores migrated to MongoDB repositories with TTL indexes, retention policies, tenant isolation indexes. 8 repositories: EventReplay, MessagingDelivery, AnalyticsExport, ObservabilityTrace, ObservabilityMetrics, ObservabilityError, AlertHistory, PipelineRun
- **Request Tracing Middleware**: Real FastAPI middleware with correlation_id propagation, latency measurement, slow endpoint detection (>1000ms), error capture, route-level performance stats
- **Production Alerting Engine**: Threshold-based alerts (Redis disconnect, event drops, messaging failures, slow endpoints, model timeouts, stale datasets, high error rate, DB issues), alert dedup with 15-min cooldown, severity mapping, runbook hints
- **Runtime Infrastructure Dashboard**: New frontend page showing event bus status, messaging provider health, persistence health (10 collections), observability summary, alert engine status
- **Updated Event Bus Dashboard**: Mode display, Redis delivery metrics, channel monitoring, replay summary
- **Updated Observability Dashboard**: Service health, endpoint performance, error summary, recent traces, trace/metric flush

## Test Coverage
- **42 unit tests** (test_production_runtime.py): Event bus, Redis, messaging providers, tracing, metrics, alerting, persistence, middleware
- **24 API integration tests** (test_production_runtime_api.py): All new endpoints validated
- **Frontend E2E**: All 3 new/updated dashboards verified with data rendering

## API Endpoints
### Runtime Infrastructure
- `GET /api/runtime/overview` — Full infrastructure status
- `GET /api/runtime/event-bus/status` — Event bus mode & health
- `GET /api/runtime/event-bus/delivery-metrics` — Delivery statistics
- `GET /api/runtime/messaging/status` — Provider health & retry queue
- `GET /api/runtime/messaging/delivery-summary` — Delivery metrics by channel
- `GET /api/runtime/persistence/health` — MongoDB collection health
- `GET /api/runtime/alerts/evaluate` — Run threshold checks
- `GET /api/runtime/alerts/candidates` — Unacknowledged alerts
- `GET /api/runtime/alerts/history` — Alert history
- `POST /api/runtime/alerts/{id}/acknowledge` — Acknowledge alert
- `GET /api/runtime/alerts/engine-status` — Engine config
- `GET /api/runtime/observability/summary` — Full observability snapshot

### Event Bus
- `GET /api/event-bus/status` — Mode, backend status, Redis config
- `GET /api/event-bus/metrics` — Published, delivered, dropped, fallback usage
- `POST /api/event-bus/publish` — Publish event
- `GET /api/event-bus/replay` — Replay events from MongoDB
- `GET /api/event-bus/replay/summary` — 24h replay summary
- `GET /api/event-bus/channels` — Active channels
- `GET /api/event-bus/sessions` — Active sessions

### Observability
- `GET /api/observability/metrics` — Dashboard metrics
- `GET /api/observability/metrics/all` — All counters, gauges, histograms
- `POST /api/observability/metrics/flush` — Flush to MongoDB
- `GET /api/observability/traces/summary` — Request tracing summary
- `GET /api/observability/traces` — Recent traces
- `GET /api/observability/traces/slow` — Slow endpoints
- `GET /api/observability/traces/hot-paths` — Hot paths
- `POST /api/observability/traces/flush` — Flush traces to MongoDB
- `GET /api/observability/errors/summary` — Error summary by severity
- `GET /api/observability/errors` — Recent errors
- `POST /api/observability/errors/{id}/resolve` — Resolve error
- `GET /api/observability/health` — Service health check
- `GET /api/observability/health/history` — Health history

## What's Still Mocked
- **Redis Pub/Sub**: In-memory fallback active (no REDIS_URL configured)
- **Messaging Providers**: Sandbox/test mode (no real Twilio/SendGrid API keys)
- **Credential Vault**: Mock implementation (no HashiCorp Vault/AWS SM)

## Remaining Backlog
- P1: Connect real Redis instance (set REDIS_URL env var)
- P1: Configure real Twilio/SendGrid/WhatsApp credentials
- P2: Integrate external monitoring (Prometheus/Grafana/Sentry)
- P2: Implement real credential vault (HashiCorp Vault)
- P3: Data pipeline scheduling integration with ml_scheduler
- P3: WebSocket broadcast via Redis for multi-instance support
- P4: Automated alert notification (email/SMS on critical alerts)

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
