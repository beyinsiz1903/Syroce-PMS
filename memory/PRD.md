# Syroce PMS - Product Requirements Document

## Original Problem Statement
Otel Yönetim Sistemi (Syroce PMS) - 5 yıldızlı otel operasyonları için kapsamlı PMS çözümü.

## Architecture
- **Frontend:** React, Tailwind CSS, Shadcn UI, Recharts, i18next, jspdf
- **Backend:** FastAPI, MongoDB (motor), JWT auth, openpyxl, WeasyPrint
- **Database:** MongoDB with tenant isolation

## What's Been Implemented

### Phase 1-3 (Previously Completed)
- Full PMS, Dashboard, Housekeeping, Finance, Channel Manager, RMS, AI, Multi-property, Night Audit, Mobile views

### Phase 4: Reporting & Analytics (Feb 2026 - COMPLETED)
- Custom Report Builder (6 data sources, dynamic columns, filters, templates)
- Excel & PDF Export (openpyxl + WeasyPrint)

### P1: i18n Conversion (Feb 2026 - COMPLETED)
- 115 page files: `useTranslation` import + hook added
- Locale files: tr.json (~900 keys), en.json expanded
- ~120 hardcoded strings converted to `t()` calls across 50+ files
- Critical pages fully converted: ReportBuilder, Reports, AIModule, BasicReports

### P2: Phase 5 - Guest Portal & Communication (Feb 2026 - COMPLETED)
- Guest Messaging System: Backend API + Frontend component
- GuestPortal updated with Messages navigation

### Bug Fix: Login Redirect (Feb 2026 - FIXED)
- Removed redundant `window.location.href` hard redirect
- React Router now handles redirect via `isAuthenticated` state
- Clean redirect: /auth → /app/dashboard

### PMSModule.js Refactoring (Feb 2026 - COMPLETED)
- 5189 → 4369 lines (820 lines extracted)
- BookingDialog.js (466 lines) → `/components/pms/BookingDialog.js`
- Guest360Dialog.js (490 lines) → `/components/pms/Guest360Dialog.js`

## Prioritized Backlog

### P2: Phase 6 - Integrations & Automation
- Channel Manager enhancements
- Payment gateway (Stripe)

### P3: Phase 7 - Security & Performance
- API rate limiting, security headers
- Load testing

### Remaining Refactoring
- Incremental i18n for ~60 pages (infrastructure ready, strings need manual t() wrapping)
- Further PMSModule decomposition (FolioViewDialog, BookingDetailDialog etc.)

## Key Files
- `/app/backend/routers/report_builder.py` - Report Builder API
- `/app/backend/routers/guest_messaging.py` - Guest Messaging API
- `/app/frontend/src/pages/ReportBuilder.js` - Report Builder UI
- `/app/frontend/src/components/GuestMessaging.js` - Messaging component
- `/app/frontend/src/components/pms/BookingDialog.js` - Extracted dialog
- `/app/frontend/src/components/pms/Guest360Dialog.js` - Extracted dialog
- `/app/frontend/src/pages/PMSModule.js` - Refactored (4369 lines)
- `/app/frontend/src/pages/AuthPage.js` - Login redirect fixed

## Test Reports
- `/app/test_reports/iteration_3.json` - Report Builder
- `/app/test_reports/iteration_4.json` - i18n + Guest Messaging
- `/app/test_reports/iteration_5.json` - Login fix + PMSModule refactor

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
