# Multi-Tenant SaaS PMS + Channel Manager — PRD

## Original Problem Statement
Multi-tenant SaaS PMS + Channel Manager with canonical data models, multi-tenant isolation, PII strict mode tracking, and comprehensive multi-language support.

## Architecture
- **Backend:** FastAPI + MongoDB (MONGO_URL from .env)
- **Frontend:** React + i18n (10 locales, 1640 keys each)
- **Channel Manager:** HotelRunner v2 (Shadow Mode), Exely (SOAP)
- **Security:** PII Strict Mode, AWS KMS encryption

## What's Been Implemented

### Core Platform
- Multi-tenant isolation with tenant-scoped data
- JWT authentication system
- Role-based access control
- Subscription/module management

### i18n System (100% Complete)
- 10 locales: en, tr, ar, de, es, fr, it, ru, pt, zh
- All 1640 keys synchronized across all languages
- pt.json and zh.json fully translated to native languages
- Static imports for guaranteed translation availability

### Channel Manager
- HotelRunner v2 connector (Shadow Mode — write_enabled=false)
- HotelRunner v1 deprecated (warnings added to all files)
- Exely SOAP API integration
- Wire failure tracking system

### Security & PII
- PII Strict Mode middleware/router
- Guest collection 99.6% encrypted
- Users and Bookings collections at 0% encryption

### Lint Fixes (Feb 2026)
- Fixed I001 import sorting in 10 deprecated HR v1 files
- Fixed F401 unused imports in wire_failure_router.py
- Fixed no-empty catch blocks in App.jsx

### Security Vulnerability Fixes (Feb 2026)
- Upgraded aiohttp 3.13.3 → 3.13.5 (CVE-2026-22815 — memory exhaustion)
- Upgraded nltk 3.9.3 → 3.9.4 (3 CVEs — recursion DoS, XSS, unauthenticated shutdown)
- Upgraded pygments 2.19.2 → 2.20.0 (CVE-2026-4539 — regex complexity)
- pip-audit now reports zero known vulnerabilities

### HotelRunner Reservation Pull & Rate Manager Fixes (Apr 2026)
- **Bug Fix: Pull Scheduler `undelivered=False` → `True`** — Now correctly fetches only undelivered reservations
- **Bug Fix: Fire confirmation (delivery ACK) was never sent** — After processing, `PUT /reservations/fire?message_uid=XXX` is now called
- **Bug Fix: `confirm_delivery` used wrong endpoint** — Changed from `RESERVATIONS_ACK` to `RESERVATIONS_FIRE`
- **Bug Fix: Pull Scheduler not auto-started at startup** — Now starts automatically with 5-min interval
- **Bug Fix: Pull Scheduler used raw `conn["token"]`** — Now resolves credentials via Secrets Manager
- **Feature: "Default room type" removal** — Added `DELETE /api/channel-manager/hr-rate-manager/room-types/{inv_code}` endpoint
- **Feature: Permission flags exposed** — `availability_update`, `price_update`, `restrictions_update` shown in Rate Manager UI with warning badges
- **Feature: Push deduplication** — Prevents duplicate HotelRunner push for same room type
- **Feature: Permission warnings** — Shows toast warnings when pushing to room types with restricted permissions

### Exely Pull Worker Tenant Context Fix (Apr 2026)
- **Bug Fix: STRICT_TENANT_MODE blocking background worker** — `exely_pull_worker.py` was accessing tenant-scoped collections (`guests`, `bookings`, `rooms`, `notifications`) without setting tenant context. Added `set_tenant_context(tenant_id)` / `clear_tenant_context()` in the worker loop. Guest imports, booking creation, and delivery confirmations now work correctly in background pulls.

## Prioritized Backlog

### P0 (Critical)
- ~~Exely Pull Worker STRICT_TENANT_MODE error~~ ✅ FIXED (Apr 2026)

### P1 (High)
- Complete 7-day shadow observation for HotelRunner v2
- Limited live write execution (single tenant)
- Full live write execution

### P2 (Medium)
- Encrypt users and bookings collections to 100%

### P3 (Low)
- Rate Manager quick toggle (Exely/HotelRunner)
- Legacy HR v1 connector removal (after full verification)

## Key API Endpoints
- GET /api/security/pii/strict-mode/config
- GET /api/security/pii/strict-mode/violations
- GET /api/security/encryption/status
- POST /api/channel-manager/hotelrunner/sync/reservations/pull (manual pull)
- GET /api/channel-manager/hotelrunner/sync/status
- DELETE /api/channel-manager/hr-rate-manager/room-types/{inv_code}

## 3rd Party Integrations
- AWS KMS (Encryption) — requires User API Key
- HotelRunner v2 — User Token active
- Exely (SOAP) — Provider credentials required

## Critical Constraints
- HotelRunner v2 MUST remain in Shadow Mode (write_enabled=false)
- All responses in Turkish
