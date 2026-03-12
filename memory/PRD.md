# Syroce Hotel PMS — Product Requirements Document

## Original Problem Statement
Enterprise hotel operating system platform refactoring and hardening for production-readiness.
Multi-phase plan to deconstruct a monolithic backend into a domain-driven architecture.

## Architecture

```
/app
├── backend/
│   ├── app.py                      # FastAPI app instance
│   ├── server.py                   # Thin entrypoint orchestrator (262 lines)
│   ├── startup.py                  # Startup/shutdown event handlers
│   ├── legacy_routes.py            # Remaining legacy endpoints (~425 endpoints, ~24.6K lines)
│   ├── core/
│   │   ├── audit.py                # (NEW) Shared audit event logger
│   │   ├── cache.py                # (NEW) Shared cache decorator
│   │   ├── database.py             # MongoDB connection
│   │   ├── security.py             # Auth & JWT
│   │   └── helpers.py              # Shared utilities
│   ├── bootstrap/
│   │   ├── router_registry.py      # Registers all routers (12 domain + legacy)
│   │   ├── dependency_container.py
│   │   └── middleware_registry.py
│   ├── domains/                    # DOMAIN ROUTERS (Phase B)
│   │   ├── channel_manager/
│   │   │   └── router.py           # CM ARI + API key endpoints (5 routes)
│   │   ├── guest/
│   │   │   ├── router.py           # VIP, blacklist, celebrations (9 routes)
│   │   │   ├── checkin_router.py   # Online check-in, upsell (4 routes)
│   │   │   └── experience_router.py # CRM, feedback, mobile app (41 routes)
│   │   ├── sales/
│   │   │   └── router.py           # Leads, marketing, events, spa (11 routes)
│   │   ├── pms/
│   │   │   ├── pos_router.py       # POS/F&B transactions (43 routes)
│   │   │   ├── mobile_router.py    # Mobile dashboard endpoints (39 routes)
│   │   │   ├── enterprise_router.py # Critical features, tasks, RBAC (50 routes)
│   │   │   └── marketplace_router.py # POS enhancements, procurement (43 routes)
│   │   ├── revenue/
│   │   │   ├── analytics_router.py # GM dashboard, anomaly detection (51 routes)
│   │   │   └── rms_router.py       # Revenue management, comp-set (31 routes)
│   │   └── hr/
│   │       └── router.py           # Staff, shifts, F&B ops (19 routes)
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
- All endpoints preserved in legacy_routes.py

### Phase B: Domain Module Separation ✅ (In Progress)
- **Batch 1**: 30 endpoints → 4 domain routers (CM, Guest, Check-in, Sales)
- **Batch 2**: 133 endpoints → 3 domain routers (POS, Mobile, Analytics)
- **Batch 3**: 184 endpoints → 5 domain routers (Enterprise, Marketplace, RMS, Experience, HR)
- **Total extracted**: 347 endpoints / 16,275 lines into 12 domain routers
- **Remaining**: 425 endpoints / 24,611 lines in legacy_routes.py

## Backlog

### P0 — Continue Phase B Extraction
- Extract remaining 425 endpoints from legacy_routes.py
- Target sections: AI Chatbot, Dynamic Pricing, WhatsApp, Reputation, Game Changers, Night Audit, etc.

### P1 — Phase C: Channel Manager Hardening
- Credential encryption, scheduled syncing, drift detection, provider failover

### P1 — Phase D: Queue & Worker Hardening
- Task idempotency, queue monitoring, dead-letter archives

### P2 — Phase E: Security Hardening
- Rate limiting, credential guarding, secret leakage detection

### P2 — Phase F: Frontend Stabilization
- Route-based code splitting, module structure

### P3 — Phase G: Operational Reliability Tests
- Production stress scenario tests in tests/runtime/

### P3 — Phase H: PMS Load Test Framework
- k6/Locust load testing scripts

## Test Credentials
| User | Email | Password |
|------|-------|----------|
| Demo Admin | demo@hotel.com | demo123 |
