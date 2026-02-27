# Syroce PMS - Product Requirements Document

## Original Problem Statement
Otel Yönetim Sistemi (Syroce PMS) - 5 yıldızlı otel operasyonları için kapsamlı PMS çözümü.

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

### P1: i18n Conversion (COMPLETED)
- 115 page files: `useTranslation` infrastructure
- ~900 key locale files (tr.json, en.json)
- ~120 hardcoded strings converted to `t()` calls

### P2: Phase 5 - Guest Portal & Communication (COMPLETED)
- Guest Messaging System (backend + frontend)
- GuestPortal messaging navigation

### Bug Fix: Login Redirect (FIXED)
- React Router handles redirect, removed window.location.href

### PMSModule.js Refactoring (COMPLETED)
- 5189 → 4369 lines
- BookingDialog (466 lines) + Guest360Dialog (490 lines) extracted

### Phase 7: Security & Performance (COMPLETED - Feb 2026)
- **Security Headers Middleware**: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy
- **JWT Token Refresh**: `/api/auth/refresh-token` endpoint
- **Audit Logging**: Login success/failure events tracked in MongoDB
- **Security Dashboard**: `/app/guvenlik` - KPI cards, API performance, security controls, event log
- **Input Sanitization Module**: XSS, NoSQL injection, path traversal protection
- **Rate Limiting**: Already active (in-memory sliding window, per-endpoint tiers)

## Prioritized Backlog

### P2: Phase 6 - Integrations & Automation
- Channel Manager enhancements
- Payment gateway (Stripe)

### Remaining Refactoring
- Incremental i18n for ~60 pages
- Further PMSModule decomposition

## Key Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/auth/login | POST | Login (audit logged) |
| /api/auth/refresh-token | POST | JWT token refresh |
| /api/security/summary | GET | Security dashboard data |
| /api/reports/builder/* | GET/POST | Report Builder CRUD |
| /api/guest/messages | GET/POST | Guest Messaging |

## Test Reports
- iteration_3: Report Builder
- iteration_4: i18n + Guest Messaging
- iteration_5: Login fix + PMS refactor
- iteration_6: Phase 7 Security & Performance

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
