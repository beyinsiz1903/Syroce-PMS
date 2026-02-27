# Syroce PMS - Product Requirements Document

## Original Problem Statement
Otel Yönetim Sistemi (Syroce PMS) - 5 yıldızlı otel operasyonları için kapsamlı PMS çözümü.

## Core Requirements
- Multi-tenant hotel management system
- Reservation management, front desk, housekeeping
- Financial reporting, invoicing, folio management
- Multi-language support (TR/EN primary)
- Role-based access control
- Mobile-responsive design

## Architecture
- **Frontend:** React, Tailwind CSS, Shadcn UI, Recharts, i18next, jspdf
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

### Phase 4: Reporting & Analytics (Feb 2026 - COMPLETED)
- **Custom Report Builder** (`/reports/builder`, `/app/rapor-olusturucu`)
  - 6 data sources: Reservations, Revenue, Guests, Rooms, Housekeeping, Folios
  - Dynamic column selection, date presets, advanced filters
  - Template save/load/delete
- **Excel & PDF Export** - openpyxl + WeasyPrint
- **Navigation** integration across all report pages

### P1: i18n Conversion (Feb 2026 - COMPLETED)
- **115 page files** now have `useTranslation` import and hook
- **Comprehensive locale files** - tr.json (~900 keys) and en.json expanded
- **Critical pages converted:** ReportBuilder.js, Reports.js, AIModule.js
- **Infrastructure ready** for incremental string replacement in remaining pages

### P2: Phase 5 - Guest Portal & Communication (Feb 2026 - COMPLETED)
- **Guest Messaging System:**
  - Backend API: `/api/guest/messages` (send, list, reply, mark-read, unread-count)
  - Frontend component: `GuestMessaging.js` (real-time chat UI)
  - Message types: general, request, complaint, feedback
  - Read/unread tracking with badge counts
  - Auto-refresh every 15 seconds
- **GuestPortal.js updated** with Messages navigation and route
- **MessagingCenter.js** fixed (broken import repaired)

### App Store Submission (Previously Completed)
- Privacy Policy page at `/gizlilik`
- App Store screenshots and content

## Prioritized Backlog

### P2: Phase 6 - Integrations & Automation
- Channel Manager enhancements
- Payment gateway (Stripe)

### P3: Phase 7 - Security & Performance
- API rate limiting, security headers
- Load testing

### Refactoring
- PMSModule.js (3400+ lines) decomposition
- Incremental i18n string replacement for remaining ~90 pages
- App Store temp endpoint cleanup

## Key API Endpoints
- `POST /api/auth/login` - Login (returns access_token)
- `GET/POST /api/reports/builder/*` - Report Builder CRUD
- `GET/POST /api/guest/messages` - Guest Messaging
- `PUT /api/guest/messages/mark-all-read` - Mark messages read
- `GET /api/guest/messages/unread-count` - Unread count

## Key Files (New/Modified)
- `/app/backend/routers/report_builder.py` - Report Builder API
- `/app/backend/routers/guest_messaging.py` - Guest Messaging API
- `/app/frontend/src/pages/ReportBuilder.js` - Report Builder UI
- `/app/frontend/src/components/GuestMessaging.js` - Messaging component
- `/app/frontend/src/pages/GuestPortal.js` - Updated with messaging
- `/app/frontend/src/locales/tr.json` - Turkish translations (expanded)
- `/app/frontend/src/locales/en.json` - English translations (expanded)
- `/app/frontend/src/config/navItems.js` - Navigation updated

## Test Credentials
| Role | Email | Password |
|------|-------|----------|
| Admin | demo@hotel.com | demo123 |
| Front Desk | frontdesk@hotel.com | staff123 |

## Test Reports
- `/app/test_reports/iteration_3.json` - Report Builder tests
- `/app/test_reports/iteration_4.json` - i18n + Guest Messaging tests
