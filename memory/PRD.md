# Syroce PMS - Product Requirements Document

## Original Problem Statement
Otel Yonetim Sistemi (Syroce PMS) - 5 yildizli otel operasyonlari icin kapsamli PMS cozumu.

## Architecture
- **Frontend:** React, Tailwind CSS, Shadcn UI, Recharts, i18next, jspdf
- **Backend:** FastAPI, MongoDB (motor), JWT auth, openpyxl, WeasyPrint
- **Database:** MongoDB with tenant isolation

## Implemented Features

### Phase 1-3 (Previously Completed)
- Full PMS, Dashboard, Housekeeping, Finance, Channel Manager, RMS, AI, Multi-property, Night Audit, Mobile views

### Phase 4: Reporting & Analytics (COMPLETED)
- Custom Report Builder, Excel & PDF Export

### Phase 5: Guest Portal & Communication (COMPLETED)
- Guest Messaging System (backend + frontend)

### Phase 7: Security & Performance (COMPLETED - Feb 2026)
- Security Headers, JWT Refresh, Audit Logging, Security Dashboard

### i18n Internationalization (COMPLETED - Feb 2026)
- 1816 t() calls, 1334 keys, 48 sections, 8 languages
- HousekeepingDetailedReports.js fully converted with 35+ new keys

### PMSModule.js Refactoring (COMPLETED - Feb 2026)
- 5189 -> 2985 lines, 12 extracted components

### Load Testing & Performance Optimization (COMPLETED - Feb 2026)
- Locust 2.43.3: 50 concurrent users, 120s, 4 roles, 34 endpoints
- Login -74.5%, Forecast -99.3%, Overall avg -33.5%, p99 -52.1%

### server.py Modularization (COMPLETED - Feb 2026)
- **Extracted 3 routers:** auth.py (620 lines), housekeeping.py (717 lines), departments.py (2956 lines)
- **Reduced server.py:** 55,671 -> 51,409 lines (-4,262 lines, -7.7%)
- **Created core/helpers.py:** Shared utilities (load_tenant_doc, resolve_tenant_features, require_module, create_audit_log)
- Fixed duplicate mock routes in comprehensive_modules_endpoints.py

### Root Directory Cleanup (COMPLETED - Feb 2026)
- Removed 152 test .py files from root directory
- Removed 30+ obsolete .md documentation files
- Clean project structure: only README.md, backend/, frontend/, docs/, memory/

## Code Architecture
```
/app
├── backend/
│   ├── server.py              # Main server (51,409 lines, modularized)
│   ├── core/
│   │   ├── database.py        # MongoDB connection
│   │   ├── security.py        # JWT auth, password hashing
│   │   ├── helpers.py         # Shared helpers (NEW)
│   │   └── sanitize.py        # Input sanitization
│   ├── routers/
│   │   ├── auth.py            # Auth endpoints (NEW - 666 lines)
│   │   ├── housekeeping.py    # Housekeeping endpoints (NEW - 745 lines)
│   │   ├── departments.py     # Department dashboards (NEW - 2986 lines)
│   │   ├── report_builder.py  # Report builder
│   │   └── guest_messaging.py # Guest messaging
│   └── models/
│       ├── enums.py           # Enumerations
│       └── schemas.py         # Pydantic models
├── frontend/
│   ├── src/
│   │   ├── locales/           # i18n files (en.json, tr.json + 6 more)
│   │   ├── components/
│   │   │   ├── pms/           # PMS sub-components
│   │   │   └── ui/            # Shadcn UI
│   │   └── pages/             # Route pages
│   └── ...
└── memory/
    └── PRD.md
```

## Prioritized Backlog

### P0 (Next)
- Phase 6: Integrations & Automation (Channel Manager enhancements, Stripe)

### P1
- Redis-based Caching (replace in-memory SimpleCache)
- Continue server.py modularization (PMS rooms, bookings, reports, finance sections)

### P2
- Remaining i18n gaps (Quick Actions buttons, minor headers)
- server.py further reduction (target: <40K lines)

## Key Endpoints
| Endpoint | Method | Router | Description |
|----------|--------|--------|-------------|
| /api/auth/login | POST | auth.py | Login (cached) |
| /api/auth/me | GET | auth.py | Current user |
| /api/security/summary | GET | auth.py | Security dashboard |
| /api/housekeeping/tasks | GET/POST | housekeeping.py | HK tasks |
| /api/housekeeping/room-status | GET | housekeeping.py | Room status board |
| /api/department/*/dashboard | GET | departments.py | Dept dashboards |
| /api/pms/dashboard | GET | server.py | PMS stats |
| /api/reports/builder/* | GET/POST | report_builder.py | Report Builder |

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
| Housekeeping | housekeeping@hotel.com | staff123 |
| Finance | finance@hotel.com | staff123 |
| Sales | sales@hotel.com | staff123 |
