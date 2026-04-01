# Syroce PMS — Product Requirements Document

## Original Problem Statement
Multi-tenant SaaS PMS + Channel Manager with canonical data models, multi-tenant isolation, PII strict mode tracking, and comprehensive multi-language support.

## User Personas
- **Hotel Admin**: Manages operations, bookings, billing, staff
- **Front Desk Agent**: Handles check-in/out, guest requests
- **Housekeeping Manager**: Room status, task assignment
- **Revenue Manager**: Pricing, forecasts, channel distribution
- **Guest**: Online check-in, portal access, feedback

## Core Requirements
1. Multi-tenant hotel PMS with full operational modules
2. Channel Manager (HotelRunner v2, Exely SOAP)
3. PII Strict Mode + Encryption tracking
4. Comprehensive i18n (10 languages)
5. Role-based access control
6. AI-powered analytics & predictions

## Architecture
```
/app
├── backend/
│   ├── security/ (pii_strict_mode, encryption)
│   ├── channel_manager/connectors/
│   │   ├── hotelrunner_v2/ (ACTIVE - Shadow Mode)
│   │   └── _deprecated_hotelrunner_v1/ (backup)
├── frontend/
│   └── src/
│       ├── i18n.jsx (static import, 10 langs)
│       ├── locales/ (10 synced JSON files, 1640 keys each)
│       ├── App.jsx (Router v6 orchestrator)
│       └── routes/
```

## What's Been Implemented

### Phase 1-5: Core PMS (DONE)
- Full PMS with 88+ modules
- 865+ API endpoints
- Dashboard, Calendar, Folio, Housekeeping, Reports
- Auth with JWT, role-based access
- Invoice & E-Fatura system
- POS, F&B Suite, Loyalty Program
- Channel Manager (HotelRunner v2 + Exely)

### i18n System (DONE - April 2026)
- **Static import fix**: Changed dynamic `import("./i18n")` to static `import "@/i18n"` in index.jsx
- **10 languages fully synchronized**: en, tr, ar, de, es, fr, it, ru, pt, zh
- **1640 keys each**, all matching
- **PT and ZH**: Completed native translations (was ~67% English fallback, now <4% — only universal terms like PMS, GDS, Excel, PDF)
- **Extra key cleanup**: Removed orphan `navKeys.revenue_autopilot` from ar, de, es, fr, it, ru

### Security (DONE)
- PII Strict Mode middleware/router
- Encryption status tracking (guests: 99.6%)

### Channel Manager (IN PROGRESS)
- HotelRunner v2: Shadow Mode active (`write_enabled=false`)
- **DO NOT ENABLE WRITES** until 7-day observation period complete

## Prioritized Backlog

### P1 (Critical)
- [ ] Complete 7-day HotelRunner v2 shadow observation
- [ ] Limited live write execution (single tenant, after criteria met)
- [ ] Full live write execution

### P2 (Important)
- [ ] Data Encryption: Encrypt `users` and `bookings` collections to 100%

### P3 (Nice to Have)
- [ ] Quick toggle button for rate manager (Exely/HotelRunner)
- [ ] Remove legacy HR v1 connector after full transition verification

## Key API Endpoints
- `GET /api/security/pii/strict-mode/config`
- `GET /api/security/pii/strict-mode/violations`
- `GET /api/security/encryption/status`

## 3rd Party Integrations
- AWS KMS (Encryption) — requires User API Key
- HotelRunner v2 — Active (Shadow Mode)
- Exely (SOAP API) — requires Provider credentials

## Test Credentials
- Frontend: `demo@hotel.com` / `demo123`
