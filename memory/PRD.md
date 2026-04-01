# Syroce PMS — Product Requirements Document

## Original Problem Statement
Multi-tenant SaaS PMS + Channel Manager for boutique hotels. Integrates with Exely (Live Push) and HotelRunner (Shadow Mode). Turkish-language responses required.

## Core Architecture
- **Backend**: FastAPI + MongoDB (Motor async driver)
- **Frontend**: React (Vite) + Shadcn/UI + TailwindCSS
- **Auth**: JWT-based (demo@hotel.com / demo123)
- **Database**: MongoDB (MONGO_URL from .env)
- **i18n**: i18next (TR/EN/AR/RU/IT/FR/ES/DE/PT/ZH) — 10 dil, tümü %100 anahtar kapsamı

## Key Integrations
- **Exely**: Live Push (SOAP API) — credentials in DB
- **HotelRunner v2**: Shadow Mode (write_enabled=false) — user token active
- **AWS KMS**: Encryption — requires user API key

## Completed Features

### Phase 1 — Core PMS (Complete)
- Room management, reservations, guest profiles, folio/billing
- Dashboard with operational metrics, reports
- Night audit, housekeeping, staff management
- Multi-property support, loyalty program

### Phase 2 — Channel Manager (Complete)
- Exely integration (Live Push mode)
- HotelRunner v2 integration (Shadow Mode)
- ARI push dashboard, rate manager, mapping manager
- Auto-Map feature for room type matching
- Wire Failure Dashboard for sync error tracking

### Phase 3 — Security & Infrastructure (Complete)
- PII Registry, masking middleware, audit logging
- Field-level encryption (guests at 99.6% coverage)
- Tenant isolation, security center, GDPR compliance
- **PII Strict Mode Enforcement** (2026-04-01)
  - DB-backed toggle for global PII masking
  - Violation tracking and reporting dashboard
  - Encryption coverage monitoring per collection
  - Whitelist management for exempt paths

### Refactoring (Complete — 2026-04-01)
- **App.jsx Decomposition**: 2170 → 229 lines
  - Routes: `/app/frontend/src/routes/routeDefinitions.jsx`
  - Auth wrappers: `/app/frontend/src/routes/ProtectedRoute.jsx`
  - Axios config: `/app/frontend/src/config/axiosConfig.js`
- **Legacy HR Connector Cleanup**:
  - Original files backed up to `_deprecated_hotelrunner_v1/`
  - Deprecation warnings added to all v1 modules
  - v2 connector remains the active implementation

### i18n Internationalization Fix (Complete — 2026-04-01)
- **Root cause**: Dynamic `import("./i18n")` in `index.jsx` caused async loading — translations not ready when App rendered
- **Fix**: Changed to synchronous `import "@/i18n"` in `index.jsx`
- Added `pt` (Portuguese) and `zh` (Chinese) to `i18n.jsx` resources
- Completed missing translations for `ar`, `de`, `es`, `fr`, `it`, `ru` (each was ~54% complete, now 100%)
- Added core translations for `pt` and `zh` (common, nav, auth, dashboard, reports, settings, folio, pms — was 0% translated, now ~33% with English fallback for less-seen sections)
- All 10 locale files now have 1640/1640 keys (100% key coverage)

## Pending / Upcoming Tasks

### P1 — HotelRunner Live Transition
1. Complete 7-day shadow observation period
2. Limited live write (single tenant/small scope)
3. Full live write execution

### P3 — UI Enhancements
- Rate Manager quick toggle (Exely ↔ HotelRunner)

### P2 — Remaining
- PII Field Encryption extended to users, bookings, reservations collections

### P3 — Cleanup
- Final removal of legacy HR v1 connector (after v2 confirmed stable)

## Key API Endpoints
- `POST /api/auth/login` — JWT login
- `GET /api/security/pii-strict-mode/config` — PII config
- `POST /api/security/pii-strict-mode/toggle` — Enable/disable strict mode
- `GET /api/security/pii-strict-mode/summary` — Violation summary
- `GET /api/security/pii-strict-mode/violations` — Violation log
- `GET /api/security/pii-strict-mode/encryption-status` — Encryption coverage
- `GET /api/security/pii-strict-mode/policy` — PII policy registry
- `GET /api/channel-manager/auto-map/suggest` — Auto-map suggestions
- `POST /api/channel-manager/auto-map/apply` — Apply mappings
- `GET /api/channel-manager/wire-failures/summary` — Wire failure stats

## Key DB Collections
- `pii_strict_mode_config` — Strict mode on/off, whitelisted paths
- `pii_strict_violations` — Violation/event log (90-day TTL)
- `exely_room_mappings`, `hotelrunner_room_mappings` — Channel mappings
├── config/
│   ├── axiosConfig.js (HTTP client setup)
│   └── navItems.jsx (sidebar navigation)
- `exely_connections` — Exely connection config

## File Structure (Key Files)
```
/app/frontend/src/
├── App.jsx (229 lines — orchestrator)
├── routes/
│   ├── routeDefinitions.jsx (all lazy imports + route configs)
│   └── ProtectedRoute.jsx (auth wrapper components)
├── i18n.jsx (10 languages: en, tr, ar, de, es, fr, it, ru, pt, zh)
├── locales/ (10 JSON files, all 1640 keys complete)
├── pages/
│   ├── PIIStrictModeDashboard.jsx
│   ├── WireFailureDashboard.jsx
│   ├── ExelyIntegration.jsx
│   └── HotelRunnerIntegration.jsx
/app/backend/
├── security/
│   ├── pii_strict_mode.py (service)
│   ├── pii_strict_mode_router.py (API)
│   ├── pii_registry.py
│   ├── field_encryption.py
│   └── pii_audit.py
├── domains/channel_manager/
│   ├── auto_map_router.py
│   └── wire_failure_router.py
├── channel_manager/connectors/
│   ├── hotelrunner/ (DEPRECATED — v1, warnings added)
│   ├── _deprecated_hotelrunner_v1/ (backup)
│   └── hotelrunner_v2/ (ACTIVE)
```
