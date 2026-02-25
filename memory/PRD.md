# Syroce PMS - Product Requirements Document

## Original Problem Statement
Otel yönetim sistemi (Syroce PMS) - Full-stack React + FastAPI + MongoDB uygulaması. Kullanıcı detaylı analiz ve rapor istedi, ardından çok fazlı iyileştirme planı uygulandı.

## Architecture
- **Frontend:** React, react-router-dom, i18next, Tailwind CSS, Shadcn UI
- **Backend:** FastAPI, MongoDB (motor), Pydantic, JWT auth
- **DevOps:** Docker, Supervisor, GitHub Actions CI/CD

## What's Been Implemented

### Phase 1: Foundation & Data Seeding (Complete)
- Data seeding mechanism (backend/seed.py)
- Security: JWT secret & CORS from .env
- Fixed IndexOptionsConflict

### Phase 2: Backend Modularization & i18n (Complete)
- Refactored server.py into core/, models/, enums/, routers/
- Created /api/folio/list endpoint
- Expanded i18n translation files (TR/EN)

### Phase 3: Frontend Optimization (Complete)
- Lazy loading for routes in App.js
- Conditional dialog rendering in PMSModule.js

### Bug Fixes (Complete)
- CI/CD pipeline fixed
- PMS/RMS rendering errors fixed
- Quick Actions buttons repaired
- Admin invoice access control fixed

### App Store Submission (Complete - Feb 25, 2026)
- Screenshots: iPhone (24), iPad (24), Apple Watch (36) = 84 files in ZIP
- Download endpoint: /api/download/screenshots
- Privacy Policy page: /gizlilik and /privacy-policy routes
- App Store Connect content prepared (Description, Keywords, etc.)

## Prioritized Backlog

### P0: Phase 4 - Reporting & Analytics
- Custom report builder
- Advanced filtering
- PDF/Excel export

### P1: i18n Completion
- Convert remaining hardcoded English strings to t() function

### P2: Phase 5 - Guest Portal & Communication
- Online check-in/out
- Guest messaging
- Service requests

### P2: Phase 6 - Integrations & Automation
- Channel Manager enhancement
- Payment gateway (Stripe)
- Automated guest emails

### P3: Phase 7 - Security & Performance
- API rate limiting
- Security headers
- Load testing

### P3: Refactoring
- PMSModule.js (~3400 lines) decomposition

## Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | Admin |
| Front Desk | frontdesk@hotel.com | staff123 | Resepsiyon |
| Housekeeping | housekeeping@hotel.com | staff123 | Kat Hizmetleri |
| Finance | finance@hotel.com | staff123 | Muhasebe |
| Sales | sales@hotel.com | staff123 | Satış |
