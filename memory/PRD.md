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

### i18n Internationalization (IN PROGRESS - Feb 2026)
- **Infrastructure:** `useTranslation` hook in all 116 page files
- **Locale files:** tr.json (1100+ keys) and en.json (1100+ keys) - fully translated
- **Key pages converted:** Dashboard.js, AuthPage.js, Settings.js (all hardcoded strings replaced with t() calls)
- **en.json fully translated:** All 20+ sections now have proper English translations
- **Bug fixed:** Settings.js ROLE_LABELS crash - t() at module level
- **Remaining:** ~80 pages still have some hardcoded strings

### PMSModule.js Refactoring (COMPLETED - Feb 2026)
- **5189 -> 3030 lines** (-41.6% reduction)
- **10 extracted components in /app/frontend/src/components/pms/:**
  1. BookingDialog.js (466 lines) - pre-existing
  2. Guest360Dialog.js (490 lines) - pre-existing
  3. BookingDetailDialog.js (~120 lines)
  4. GuestInfoDialog.js (~200 lines)
  5. FindRoomDialog.js (~130 lines)
  6. PaymentDialog.js (~100 lines)
  7. BulkRoomsDialog.js (~150 lines)
  8. MaintenanceDialog.js (~85 lines)
  9. RoomBlockDialogs.js (~100 lines, 2 exports)
  10. CompanyDialog.js (~40 lines)
  11. HKTaskDialog.js (~50 lines)
- Duplicate Maintenance Dialog removed

### Bug Fix: Login Redirect (FIXED)
- React Router handles redirect

## Prioritized Backlog

### P0 (Next)
- Continue i18n hardcoded string conversion for remaining ~80 pages

### P1
- Phase 6: Integrations & Automation (Channel Manager, Stripe)

### P2
- Load Testing (k6 / Locust)

## Key Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/auth/login | POST | Login |
| /api/auth/refresh-token | POST | JWT refresh |
| /api/pms/dashboard | GET | PMS stats |
| /api/reports/builder/* | GET/POST | Report Builder |
| /api/security/summary | GET | Security dashboard |

### Deployment Fix (Feb 2026)
- Removed `emergentintegrations==0.1.0` and `litellm==1.80.0` from requirements.txt (CI/CD can't install from custom PyPI index)
- Wrapped bare `emergentintegrations` import in server.py with try/except
- yarn.lock verified in sync with package.json

## Test Reports
- iteration_4: i18n + Settings bug fix (100% pass)
- iteration_7: PMSModule.js refactoring (100% pass)

## Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
