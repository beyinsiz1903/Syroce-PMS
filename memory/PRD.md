# Syroce PMS — Product Requirements Document

## Original Problem Statement
Cloud PMS + Channel Manager integration platform. User acts as principal SaaS architect building a production-grade HotelRunner integration engine with operational maturity features.

## Architecture
- Backend: FastAPI + MongoDB (async)
- Frontend: React + Tailwind + Shadcn/UI
- Pattern: Connector-first, domain-driven design
- Encryption: AES-256-GCM for credential security

## Code Structure
```
backend/channel_manager/
├── application/          # Business logic services
│   ├── alerting_service.py
│   ├── connector_service.py
│   ├── error_queue_service.py
│   ├── event_sync_service.py
│   ├── historical_metrics_service.py
│   ├── inventory_sync_service.py
│   ├── mapping_service.py
│   ├── multi_property_service.py
│   ├── observability_service.py
│   ├── production_readiness_service.py
│   ├── provider_adapters.py
│   ├── reconciliation_service.py
│   ├── reliability_service.py
│   ├── reservation_import_service.py
│   ├── sandbox_validation_service.py
│   ├── scheduled_import_service.py     # NEW: Sprint 3
│   ├── scheduler_service.py
│   └── webhook_service.py
├── connectors/hotelrunner/
│   ├── auth.py
│   ├── client.py
│   ├── contract_errors.py              # NEW: Sprint 1
│   ├── environment_config.py           # NEW: Sprint 1
│   ├── errors.py
│   ├── rate_limit.py
│   ├── retry_policy.py
│   ├── xml_builder.py
│   └── xml_parser.py
├── domain/models/
│   ├── audit.py
│   ├── canonical.py
│   ├── connector_account.py
│   ├── credential_security.py          # NEW: Sprint 4
│   ├── reservation_import.py
│   └── sync.py
├── infrastructure/
│   ├── credential_vault.py
│   ├── encryption_service.py
│   ├── indexes.py
│   ├── rbac.py
│   └── repository.py
└── interfaces/
    ├── router_registry.py              # NEW: Sprint 2
    ├── router.py                       # LEGACY (preserved)
    └── routers/                        # NEW: Sprint 2
        ├── alert_router.py
        ├── audit_router.py
        ├── connector_router.py
        ├── metrics_router.py
        ├── reservation_router.py
        ├── scheduler_router.py
        └── sync_router.py
```

## Completed Features

### Core Platform (Phase 1-3)
- Channel Manager v2 connector-first architecture
- HotelRunner client with rate limiting, retry, audit
- Inventory Sync Engine (delta sync, coalescing, batching)
- Reservation Import Engine (idempotency, duplicate protection)
- Entity mapping service with validation

### Operational Maturity (Phase 4-6)
- Historical metrics storage with retention
- Alerting engine with rules and severity levels
- Connector reliability monitoring (uptime, MTTR, MTBF)
- Sandbox validation (10-check suite)
- Multi-property dashboard
- Integration audit log
- Error queue with bulk operations
- Webhook ingestion
- Production readiness checker
- RBAC for credential access

### Sprint Implementation (2026-03-11)

#### Sprint 1: HotelRunner Sandbox Validation Enhancement
- Environment config: mock/sandbox/production with per-env settings
- Enhanced readiness report with warnings, contract mismatches
- Ops integration: validation results -> metrics, alerting, reliability
- Typed provider contract errors (InvalidXml, MissingField, SchemaMismatch, ProviderError, UnknownFormat)

#### Sprint 2: Router Refactoring
- Broke 1800+ line router.py into 7 feature-based routers
- Central router_registry.py for registration
- All endpoint URLs preserved (zero breaking changes)
- 26 API tests verify no regression

#### Sprint 3: Scheduled Reservation Import Jobs
- Background import job system with lifecycle: pending -> running -> completed/retrying/failed
- Duplicate job prevention via in-memory lock
- Retry with exponential backoff (max 3)
- Import failure spike -> alerting engine
- Cron safety-net inventory sync
- Per-connector configurable polling interval
- New Import Jobs tab in Admin Panel

#### Sprint 4: Credential Security Hardening
- ConnectorCredential, EncryptedSecret, SecretRotationLog models
- AES-256-GCM encryption at rest
- Masked credential viewing (UI + API)
- RBAC-enforced credential operations
- Secure rotation with audit trail
- Post-rotation auto-validation

### Frontend
- 13-tab Admin Control Panel (Sync Health, Reservations, Alerts, Reliability, Reconciliation, Scheduler, Import Jobs, Credentials, Error Queue, Observability, Readiness, Sandbox Validation, Multi-Property)

## Test Coverage
- 40 unit tests (test_sprint_suite.py) — 100% pass
- 26 API integration tests (test_sprint_features_api.py) — 100% pass
- 21 reservation engine tests — 100% pass
- 19 reservation API tests — 100% pass

## Remaining Work

### P1 - Next
- Alert delivery channels (email via SendGrid, SMS via Twilio, webhooks)
- Real HotelRunner sandbox credentials for E2E validation

### P2 - Enhancement
- UI/UX polish for all admin tabs
- Advanced data visualizations
- Background scheduler worker (cron/APScheduler)

### P3 - Future
- Multi-language support (i18n)
- Performance optimization
- Report builder
