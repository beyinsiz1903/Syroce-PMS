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
- Custom Report Builder (6 data sources, dynamic columns, filters, templates)
- Excel & PDF Export

### Phase 5: Guest Portal & Communication (COMPLETED)
- Guest Messaging System (backend + frontend)

### Phase 7: Security & Performance (COMPLETED - Feb 2026)
- Security Headers, JWT Refresh, Audit Logging, Security Dashboard

### i18n Internationalization (COMPLETED - Feb 2026)
- **Infrastructure:** `useTranslation` hook in all 116 page files
- **Locale files:** tr.json and en.json - 1334 keys across 48 sections
- **All 116 pages converted** - 1816 t() calls total
- **8 supported languages:** EN, TR, AR, RU, IT, FR, ES, DE

### PMSModule.js Refactoring (COMPLETED - Feb 2026)
- **5189 -> 3030 -> 2985 lines** (under 3000 target)
- 12 extracted components in /app/frontend/src/components/pms/ (GuestsTab added)

### i18n Locale File Cleanup (COMPLETED - Feb 2026)
- Removed redundant `frontend/src/i18n/locales/` directory

### Load Testing (COMPLETED - Feb 2026)
- **Tool:** Locust 2.43.3
- **Config:** 50 concurrent users, 120s duration, 4 user roles
- **Results:** 2,293 requests, 0% error rate, 19.13 RPS
- **Median response:** 7ms, p95: 3,600ms, p99: 7,300ms
- **34 endpoints tested** across all PMS modules
- **Report:** /app/test_reports/LOAD_TEST_REPORT.md

### CI/CD Pipeline Fix (COMPLETED - Feb 2026)
- Backend dependencies cleaned, yarn.lock synced, .gitignore restored

## Prioritized Backlog

### P1 (Next)
- Phase 6: Integrations & Automation (Channel Manager, Stripe)

### P2
- Performance optimizations based on load test findings (login caching, report caching, AI prediction caching)

## Key Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/auth/login | POST | Login |
| /api/auth/refresh-token | POST | JWT refresh |
| /api/pms/dashboard | GET | PMS stats |
| /api/reports/builder/* | GET/POST | Report Builder |
| /api/security/summary | GET | Security dashboard |

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
| Housekeeping | housekeeping@hotel.com | staff123 |
| Finance | finance@hotel.com | staff123 |
| Sales | sales@hotel.com | staff123 |
