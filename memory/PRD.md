# Syroce PMS - Product Requirements Document

## Original Problem Statement
Otel Yönetim Sistemi (Syroce PMS) - 5 yıldızlı otel operasyonları için kapsamlı bir PMS çözümü.

## Core Requirements
- Multi-tenant hotel management system
- Reservation management, front desk, housekeeping
- Financial reporting, invoicing, folio management
- Multi-language support (TR/EN primary)
- Role-based access control
- Mobile-responsive design

## Architecture
- **Frontend:** React, Tailwind CSS, Shadcn UI, Recharts, i18next
- **Backend:** FastAPI, MongoDB (motor), JWT auth, openpyxl, WeasyPrint
- **Database:** MongoDB with tenant isolation

## What's Been Implemented

### Phase 1-3 (Previously Completed)
- Full PMS module (reservations, rooms, check-in/out)
- Dashboard with KPIs
- Housekeeping management
- Finance & invoicing
- Channel Manager
- Revenue Management (RMS)
- AI modules
- Multi-property support
- Night Audit
- Mobile views
- i18n (partial)

### Phase 4: Reporting & Analytics (Feb 2026 - COMPLETED)
- **Custom Report Builder** (`/reports/builder`, `/app/rapor-olusturucu`)
  - 6 data sources: Reservations, Revenue, Guests, Rooms, Housekeeping, Folios
  - Dynamic column selection with type indicators
  - Date range presets (Today, This Week, This Month, Last 30/90 Days, Quarter, YTD)
  - Advanced filters with operators (eq, ne, gt, gte, lt, lte, contains, in)
  - Sort and limit configuration
  - Inline results table with summary statistics
  - Template save/load/delete functionality
- **Excel Export** - Formatted workbook with headers, data styling, summary row
- **PDF Export** - Professional HTML-to-PDF via WeasyPrint
- **Navigation** - Added to main nav, Reports tabs, BasicReports sidebar

### App Store Submission (Previously Completed)
- Privacy Policy page at `/gizlilik`
- App Store screenshots
- App Store Connect content

## Prioritized Backlog

### P1: i18n Hardcoded String Conversion
- Convert remaining English strings to `t()` function
- Reports, AI modules, Guest Portal

### P2: Phase 5 - Guest Portal & Communication
- Online check-in/out
- Guest messaging

### P2: Phase 6 - Integrations & Automation
- Channel Manager enhancements
- Payment gateway (Stripe)

### P3: Phase 7 - Security & Performance
- API rate limiting, security headers
- Load testing

### Refactoring
- PMSModule.js (3400+ lines) decomposition
- App Store temp endpoint cleanup

## Test Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |
| Housekeeping | housekeeping@hotel.com | staff123 |
| Finance | finance@hotel.com | staff123 |
| Sales | sales@hotel.com | staff123 |

## Key API Endpoints
- `POST /api/auth/login` - Login (returns access_token)
- `GET /api/reports/builder/config` - Report builder config
- `POST /api/reports/builder/generate` - Generate custom report
- `POST /api/reports/builder/export/excel` - Excel export
- `POST /api/reports/builder/export/pdf` - PDF export
- `GET/POST/DELETE /api/reports/builder/templates` - Template CRUD
- `GET /api/reports/basic-dashboard` - Basic reports data
- `GET /api/reports/flash-report` - Flash report

## Key Files
- `/app/backend/routers/report_builder.py` - Report Builder API
- `/app/frontend/src/pages/ReportBuilder.js` - Report Builder UI
- `/app/frontend/src/pages/Reports.js` - Advanced Reports page
- `/app/frontend/src/pages/BasicReports.js` - Basic Reports page
- `/app/frontend/src/config/navItems.js` - Navigation config
- `/app/backend/server.py` - Main backend (55K lines)
