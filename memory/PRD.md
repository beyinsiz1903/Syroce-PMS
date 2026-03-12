# Syroce Hotel PMS — Product Requirements Document

## Original Problem Statement
Enterprise hotel operating system platform refactoring and hardening for production-readiness.
Multi-phase plan to deconstruct a monolithic backend into a domain-driven architecture.

## Architecture

```
/app
├── backend/
│   ├── app.py                      # FastAPI app instance + OpenAPI tag config
│   ├── server.py                   # Thin entrypoint orchestrator (262 lines)
│   ├── startup.py                  # Startup/shutdown event handlers
│   ├── legacy_routes.py            # Compatibility layer (0 endpoints, shared models only)
│   ├── core/
│   │   ├── audit.py                # Shared audit event logger
│   │   ├── cache.py                # Shared cache decorator
│   │   ├── database.py             # MongoDB connection
│   │   ├── security.py             # Auth & JWT
│   │   ├── helpers.py              # Shared utilities
│   │   └── utils.py                # Excel, file utilities
│   ├── bootstrap/
│   │   ├── router_registry.py      # Registers all 30 domain routers
│   │   ├── dependency_container.py
│   │   └── middleware_registry.py
│   ├── domains/                    # DOMAIN ROUTERS (Phase B COMPLETE)
│   │   ├── ai/
│   │   │   └── router.py           # AI/ML, predictions, sentiment (45 routes)
│   │   ├── admin/
│   │   │   └── router.py           # Tenants, subscriptions, RBAC (42+ routes)
│   │   ├── channel_manager/
│   │   │   ├── router.py           # CM ARI + API key (5 routes)
│   │   │   └── operations_router.py # OTA connections, room mapping (18 routes)
│   │   ├── guest/
│   │   │   ├── router.py           # VIP, blacklist, celebrations (9 routes)
│   │   │   ├── checkin_router.py   # Online check-in, upsell (4 routes)
│   │   │   ├── experience_router.py # CRM, feedback, mobile (41 routes)
│   │   │   ├── operations_router.py # Loyalty, NPS, preferences (34 routes)
│   │   │   └── messaging/
│   │   │       └── router.py       # WhatsApp, SMS, email (12 routes)
│   │   ├── sales/
│   │   │   ├── router.py           # Leads, marketing, events (11 routes)
│   │   │   └── crm_router.py       # Sales CRM, corporate (12 routes)
│   │   ├── pms/
│   │   │   ├── pos_router.py       # POS/F&B core (43 routes)
│   │   │   ├── pos_fnb_router.py   # POS/F&B extended (29 routes)
│   │   │   ├── mobile_router.py    # Mobile dashboard (39 routes)
│   │   │   ├── enterprise_router.py # Critical features, RBAC (50 routes)
│   │   │   ├── marketplace_router.py # Procurement (43 routes)
│   │   │   ├── dashboard_router.py  # Dashboard, executive, GM KPIs (21 routes)
│   │   │   ├── frontdesk_router.py  # Check-in, check-out, folio (25 routes)
│   │   │   ├── housekeeping_router.py # Tasks, staff perf (19 routes)
│   │   │   ├── night_audit_router.py # Logs, night audit (7 routes)
│   │   │   ├── notification_router.py # Notifications, inbox (15 routes)
│   │   │   ├── groups_router.py    # Group/block reservations (14 routes)
│   │   │   ├── calendar_router.py  # Calendar, rate codes (14 routes)
│   │   │   ├── approvals_router.py # Approval workflows (9 routes)
│   │   │   ├── maintenance_router.py # Maintenance, IoT (16 routes)
│   │   │   └── misc_router.py      # Multi-property, HR, payments (33 routes)
│   │   ├── revenue/
│   │   │   ├── analytics_router.py # GM dashboard, anomaly (51 routes)
│   │   │   ├── rms_router.py       # Revenue management (31 routes)
│   │   │   └── pricing_router.py   # Rates, pricing, RMS (43 routes)
│   │   └── hr/
│   │       └── router.py           # Staff, shifts (19 routes)
│   ├── routers/                    # Original routers (pre-existing)
│   ├── security/                   # (Scaffolded)
│   ├── workers/                    # (Scaffolded)
│   └── tests/
│       └── runtime/                # (Scaffolded)
├── frontend/
│   └── ...
└── load_tests/                     # (Scaffolded)
```

## Completed Phases

### Phase A: Entrypoint Refactoring ✅
- Reduced server.py from 42K to 262 lines
- Created app.py, startup.py, bootstrap modules

### Phase B: Domain Module Separation ✅ COMPLETE
- **Wave 1**: 347 endpoints → 12 domain routers
- **Wave 2**: 404 endpoints → 18 new domain routers
- **Total**: 751 endpoints extracted into 30 domain routers
- **legacy_routes.py**: 0 endpoints remaining (only shared model definitions)
- **Auth shadow cleanup**: Removed 16 shadow function definitions
- **Duplicate audit**: Removed 23 cross-file + 5 intra-file duplicate endpoints
- **OpenAPI tag grouping**: 18 domain-based tags configured
- **Testing**: 31/31 tests passed (backend + frontend)

## Backlog

### P1 — Phase C: Channel Manager Hardening
- Credential encryption, scheduled syncing, drift detection, provider failover

### P1 — Phase D: Queue & Worker Hardening
- Task idempotency, queue monitoring, dead-letter archives

### P2 — Phase E: Security Hardening
- API rate limiting, tenant query guards, credential guarding, secret leakage detection

### P2 — Phase F: Frontend Stabilization
- Audit frontend dependencies, route-based code splitting

### P2 — Model Migration
- Move remaining 71 inline Pydantic models from legacy_routes.py to models/ package
- Domain service wiring (router → service → repository pattern)

### P3 — Phase G: Operational Reliability Tests
- Write runtime stress test code in backend/tests/runtime/

### P3 — Phase H: PMS Load Test Framework
- Write k6/Locust scripts in load_tests/

## Key Metrics
- **Total API operations**: 1,768
- **OpenAPI tags**: 108 (18 domain-organized + legacy)
- **Domain routers**: 30
- **Legacy endpoints remaining**: 0
