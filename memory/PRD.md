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

### PMSModule.js Refactoring (COMPLETED - Feb 2026)
- 5189 -> 2985 lines, 12 extracted components

### Load Testing & Performance Optimization (COMPLETED - Feb 2026)
- **Locust 2.43.3:** 50 concurrent users, 120s, 4 roles, 34 endpoints
- **Before:** 2,293 req, 19.13 RPS, Avg 626ms, Login p50: 5,500ms
- **After:** 2,472 req, 20.77 RPS, Avg 416ms, Login p50: 1,400ms
- **Optimizations applied:**
  - Login session cache (in-memory, 5min TTL) - bcrypt bypass on repeat logins
  - AI occupancy prediction cache (15min TTL)
  - AI guest patterns cache (15min TTL)
  - Password change invalidates login cache
- **Results:** Login -74.5%, Forecast -99.3%, Overall avg -33.5%, p99 -52.1%

## Prioritized Backlog

### P1 (Next)
- Phase 6: Integrations & Automation (Channel Manager, Stripe)

## Key Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/auth/login | POST | Login (cached) |
| /api/pms/dashboard | GET | PMS stats |
| /api/reports/builder/* | GET/POST | Report Builder |
| /api/ai/pms/occupancy-prediction | GET | AI prediction (cached 15min) |

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
| Housekeeping | housekeeping@hotel.com | staff123 |
| Finance | finance@hotel.com | staff123 |
| Sales | sales@hotel.com | staff123 |
