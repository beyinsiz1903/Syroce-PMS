# Hotel Operating System - PRD

## Original Problem Statement
Enterprise-grade Hotel Operating System with PMS Core, Channel Manager, Operational Event Architecture, Revenue ML Pipeline, Revenue Autopilot, Guest Intelligence, Messaging Gateway, Multi-Property Platform, Analytics Export, and Production Hardening.

## User Personas
- Hotel General Manager (super_admin)
- Revenue Manager (revenue)
- Front Desk Staff (front_desk)
- Housekeeping Manager (housekeeping)
- Finance Manager (finance)
- Maintenance Staff (maintenance)

## Core Modules (Completed)
1. PMS Core - Reservations, rooms, guests, folios
2. Channel Manager - OTA integrations, rate/availability sync
3. Operational Event Architecture - Real-time event broadcasting
4. Revenue ML Pipeline - ML-driven pricing recommendations
5. Revenue Autopilot - Auto-apply pricing with approval queue
6. Guest Intelligence - Guest profiling, churn risk, upsell
7. Messaging Gateway - SMS/Email/WhatsApp (mocked providers)
8. Multi-Property Platform - Cross-property management
9. Analytics Export - CSV/Excel/PDF report generation
10. ML Scheduler - Cron-based model execution scheduling

## Platform Hardening Modules (Completed - 2026-03-12)

### Data Pipeline
- Feature Store: Revenue, Operational, Guest Intelligence feature extraction from MongoDB
- Dataset Generator: Versioned training datasets with lineage tracking
- Model Registry: Model version tracking, deployment, stale detection
- Prediction Service: Confidence monitoring, stale prediction alerts
- Pipeline Orchestrator: Full pipeline execution (extract→dataset→train→deploy)
- API: /api/data-pipeline/*

### Redis Pub/Sub Event Bus
- Event Bus Abstraction: Unified interface with in-memory fallback
- Redis Backend: Production-ready Redis Pub/Sub integration (graceful fallback)
- Event Replay: Reconnection recovery, missed event delivery
- Tenant-Aware Routing: Property-scoped, role-based event filtering
- API: /api/event-bus/*

### Production Observability
- Metrics Collector: WebSocket latency, ML execution time, autopricing rate, messaging delivery, sync lag, event throughput
- Distributed Tracing: Request lifecycle tracking with correlation IDs
- Error Tracker: Centralized error aggregation by severity/module
- Service Health: Aggregated health monitoring (MongoDB, Event Bus, ML Pipeline, Messaging, Autopilot, Error Rate)
- API: /api/observability/*

### Multi-Tenant Security Hardening
- Tenant-Scoped Queries: Query guards, cross-tenant detection, isolation scoring
- Property-Scoped RBAC: Role-based permissions per property
- Credential Vault: Encrypted storage, rotation tracking, leakage detection
- Data Masking: Sensitive field masking (passwords, emails, cards)
- Audit Completeness: Coverage scoring across all auditable operations
- API: /api/security-hardening/*

## Architecture
```
/app/backend/
├── modules/
│   ├── data_pipeline/         (feature_store, dataset_generator, model_registry, prediction_service, pipeline_orchestrator)
│   ├── event_bus/             (abstraction, redis_pubsub, event_replay, routing)
│   ├── observability/         (metrics_collector, distributed_tracing, error_tracker, service_health)
│   ├── security_hardening/    (tenant_scoped_queries, property_permissions, credential_vault, data_masking, audit_completeness)
│   └── enterprise/            (messaging_gateway, ml_scheduler, revenue_autopilot, analytics_export, websocket_scaling)
├── routers/                   (data_pipeline, event_bus, observability, security_hardening + existing)
└── tests/                     (test_platform_hardening.py - 40 tests, test_platform_hardening_api.py - 25 tests)

/app/frontend/src/pages/
├── DataPipelineDashboard.js
├── EventBusDashboard.js
├── ObservabilityDashboard.js
└── SecurityHardeningDashboard.js
```

## Tech Stack
- Backend: FastAPI + MongoDB (motor) + APScheduler
- Frontend: React + Shadcn/UI + Tailwind CSS
- Event Bus: Redis Pub/Sub (with in-memory fallback)
- Auth: JWT-based

## Testing
- Unit Tests: 40 (test_platform_hardening.py) - 100% pass
- API Tests: 25 (test_platform_hardening_api.py) - 100% pass
- E2E Frontend: All 4 dashboards validated
- Previous Enterprise Tests: 33 (test_enterprise_features.py) - 100% pass

## Mocked Components
- ML model training (generates synthetic metrics)
- Prediction service (rule-based synthetic predictions)
- Redis Pub/Sub (in-memory fallback when Redis unavailable)
- Messaging providers (Twilio/SendGrid not connected)

## Prioritized Backlog
- P1: Activate real Redis Pub/Sub (requires Redis instance)
- P1: Activate real Twilio/SendGrid integrations
- P2: Migrate enterprise module in-memory stores to MongoDB
- P2: Connect observability metrics to real middleware (request tracing)
- P3: Connect cross-module enrichment to new pipeline/event bus
- P3: Production deployment configuration (Redis, secrets management)
