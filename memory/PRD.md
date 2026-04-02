# Multi-Tenant SaaS PMS + Channel Manager — PRD

## Original Problem Statement
Multi-tenant SaaS PMS + Channel Manager with canonical data models, multi-tenant isolation, PII strict mode tracking, and comprehensive multi-language support.

## Architecture
- **Backend:** FastAPI + MongoDB (MONGO_URL from .env)
- **Frontend:** React + i18n (10 locales, 1640 keys each)
- **Channel Manager:** HotelRunner v2 (LIVE MODE), Exely (SOAP)
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
- HotelRunner v2 connector (LIVE MODE — shadow_mode=false, write_enabled=true)
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
- **Bug Fix: STRICT_TENANT_MODE blocking background worker** — `exely_pull_worker.py` was accessing tenant-scoped collections without setting tenant context. Fixed with `set_tenant_context(tenant_id)` / `clear_tenant_context()`.

### HotelRunner Shadow Mode → Live Mode Transition (Apr 2026)
- **Shadow Mode Disabled** — `connector_feature_flags` updated: `shadow_mode=false`, `write_enabled=true`, `connector_enabled=true`
- **Room Type Mappings Created** — 3 HotelRunner rooms mapped to PMS:
  - HR:1271567 (Corner Süit) → Suite
  - HR:1271568 (Standart Oda) → Standard
  - HR:1271569 (Deluxe Oda) → Deluxe
- **Rate Plan Mappings Created** — All 3 HR rooms mapped with Ana Fiyat rate
- **Bug Fix: STRICT_TENANT_MODE in ingest pipeline** — Added `set_tenant_context(tenant_id)` to:
  - `pipeline.py:process_event()` — Main pipeline entry
  - `pipeline.py:_trigger_import_bridge()` — Import bridge trigger
  - `hotelrunner_webhook.py:_persist_and_process()` — Webhook handler
  - `hotelrunner_webhook.py:pull_for_tenant()` — Pull scheduler
  - `import_bridge_service.py:auto_import_reservation_to_pms()` — Auto-import function
- **Bug Fix: Double-claim race condition** — Import retry worker was claiming record then `auto_import_reservation_to_pms` re-claimed it, causing failure. Added `pre_claimed_record` parameter to bypass second claim.
- **Bug Fix: Booking fields missing** — Import bridge now stores:
  - `room_type`: PMS room type name (not provider code)
  - `channel`: Source system (e.g., booking.com)
  - `external_reservation_id`: Provider's reservation number
- **Feature: Guest auto-creation** — Import bridge now creates guest records when importing OTA reservations (with duplicate detection by email/phone)
- **End-to-end verified**: Webhook → Pipeline → Import Bridge → Atomic Booking → Guest Creation

### HotelRunner Sync & Calendar Improvements (Apr 2026)
- **Feature: 30-second polling** — HR pull scheduler interval decreased from 5 min to 30 sec
- **Feature: Unassigned room imports** — OTA bookings now arrive as unassigned (room_id=None) for manual blocking
- **Feature: Import notifications** — notification_events_service.emit() fires on successful reservation import
- **Feature: Catch-up pull** — Scheduler fetches all recent reservations (not just undelivered) to prevent dropped bookings during HR push failures

### Calendar Vibrant Color Update (Apr 2026)
- **UI: Vibrant booking bar colors** — Gray (#9ca3af) replaced with status-based colors: Blue (confirmed), Orange (today arrivals), Green (checked-in), Teal (guaranteed), Light red (past)
- **UI: Blue-tinted room type headers** — Replaced amber/yellow backgrounds with blue-50 tones
- **UI: Updated legend** — Now shows 4 statuses: Iceride, Bugun Gelis, Onaylanmis, Gecmis/Check-out
- **UI: Lighter past dates** — Reduced gray intensity from gray-200 to gray-100

### Calendar Occupancy Fix & Compact UI (Apr 2026)
- **Bug Fix: Occupancy counter excluded unassigned bookings** — Room type header (X/Y indicator) now counts both assigned and unassigned bookings for accurate occupancy display
- **UI: Compact calendar grid** — Cell width reduced from 96px to 72px, booking bar height from 46px to 30px, room rows from 52px to 38px
- **UI: Bold reservation names** — Guest names on booking bars now use font-extrabold (font-weight: 800)
- **UI: Three-state occupancy indicator** — Green (empty), orange (partial), red (full) dot colors in room type header


## Prioritized Backlog

### P1 (High)
- None critical at this time

### P2 (Medium)
- Encrypt users and bookings collections to 100%

### P3 (Low)
- Rate Manager quick toggle (Exely/HotelRunner)
- Legacy HR v1 connector removal (after full verification)
- Channel Manager Dashboard — recent reservations, failed imports, connection health metrics

## Key API Endpoints
- GET /api/security/pii/strict-mode/config
- GET /api/security/pii/strict-mode/violations
- GET /api/security/encryption/status
- POST /api/channel-manager/hotelrunner/sync/reservations/pull (manual pull)
- GET /api/channel-manager/hotelrunner/sync/status
- POST /api/channel-manager/hotelrunner/webhooks/reservations (webhook receiver)
- DELETE /api/channel-manager/hr-rate-manager/room-types/{inv_code}
- GET /api/channel/hotelrunner-v2/flags (feature flags)

## 3rd Party Integrations
- AWS KMS (Encryption) — requires User API Key
- HotelRunner v2 — User Token active, LIVE MODE
- Exely (SOAP) — Provider credentials required

## Critical Constraints
- All responses in Turkish
- Database was wiped clean for fresh testing (Apr 2026)
- Latest test report: /app/test_reports/iteration_179.json
