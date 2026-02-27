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
- GuestPortal messaging navigation

### Phase 7: Security & Performance (COMPLETED - Feb 2026)
- Security Headers Middleware, JWT Token Refresh, Audit Logging, Security Dashboard
- Input Sanitization Module, Rate Limiting

### i18n Internationalization (IN PROGRESS - Feb 2026)
- **Infrastructure:** `useTranslation` hook injected into all 116 page files
- **Locale files:** tr.json (Turkish) and en.json (English) - ~1100+ keys each
- **en.json fully translated:** All sections now have proper English translations (was Turkish before)
- **Key pages fully converted:** Dashboard.js, AuthPage.js, Settings.js
- **New keys added:** dashboard (28 new), auth (40+ new), settings (30+ new)
- **Bug fixed:** Settings.js ROLE_LABELS t() outside component - moved to getRoleLabel() inside component
- **Remaining:** ~80 pages still have hardcoded strings that should use t() calls

### PMSModule.js Refactoring (IN PROGRESS - Feb 2026)
- **Starting size:** 5189 lines
- **Current size:** 3918 lines (-1271 lines, -24.5% reduction)
- **Extracted components:**
  - BookingDialog.js (466 lines)
  - Guest360Dialog.js (490 lines)
  - GuestInfoDialog.js (~200 lines) - NEW
  - BookingDetailDialog.js (~120 lines) - NEW
- **Duplicate removed:** Maintenance Work Order Dialog (was duplicated, -93 lines)
- **Remaining:** More dialogs can be extracted (FolioView, FindRoom, BulkRooms, etc.)

### Bug Fix: Login Redirect (FIXED)
- React Router handles redirect, removed window.location.href

## Prioritized Backlog

### P0 (Next)
- Continue i18n hardcoded string conversion for remaining pages
- Continue PMSModule.js refactoring (target: <3000 lines)

### P1
- Phase 6: Integrations & Automation
  - Channel Manager enhancements
  - Payment gateway (Stripe)

### P2
- Load Testing (k6 or Locust)

## Key Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/auth/login | POST | Login (audit logged) |
| /api/auth/refresh-token | POST | JWT token refresh |
| /api/security/summary | GET | Security dashboard data |
| /api/reports/builder/* | GET/POST | Report Builder CRUD |
| /api/guest/messages | GET/POST | Guest Messaging |
| /api/pms/dashboard | GET | PMS Dashboard stats |

## Test Reports
- iteration_1-3: Previous phases
- iteration_4: i18n conversion + Settings.js bug fix (100% pass)

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
