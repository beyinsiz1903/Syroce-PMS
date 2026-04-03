# Multi-Tenant SaaS PMS + Channel Manager — PRD

## Original Problem Statement
Multi-tenant SaaS PMS + Channel Manager with canonical data models, multi-tenant isolation, PII strict mode tracking, and comprehensive multi-language support.

## Architecture
- **Backend:** FastAPI + MongoDB (MONGO_URL from .env)
- **Frontend:** React + i18n (10 locales, 1640 keys each)
- **Channel Manager:** HotelRunner v2 (LIVE MODE), Exely (SOAP)
- **Security:** PII Strict Mode, AES-256-GCM field encryption

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

### Security & PII — Field Encryption (100% Complete)
- PII Strict Mode middleware/router
- **Guest collection: 100% encrypted** (email, phone, id_number, passport, address, etc.)
- **Users collection: 100% encrypted** (email, phone)
- **Bookings collection: 100% encrypted** (guest_email, guest_phone, billing_address, billing_tax_number)
- **Reservations collection: 0 documents** (encrypted on insert)
- Hash-based search indexes for encrypted fields (_hash_email, _hash_phone, etc.)
- Dual-read pattern: auth/search works with both encrypted and plaintext data
- Auto-encryption on new inserts (auth register, admin create, OTA import, seed data)
- AES-256-GCM with HMAC-SHA256 search hashes

### Calendar Vibrant Color Update (Apr 2026)
- Vibrant booking bar colors (Blue, Orange, Green, Teal, Red) by status
- Blue-tinted room type headers
- Updated legend and lighter past dates
- Compact grid with bold reservation names and three-state occupancy dots

### HotelRunner Live Integration
- Shadow Mode disabled, Live Mode active
- Room/rate mappings created
- 30-second polling, unassigned imports, notifications
- End-to-end verified webhook pipeline
- Per-room cancellation detection for multi-room reservations
- Modification/cancellation notification sync from Phase B pull
- room_type_id matching for calendar display of OTA imports
- Three-tier global/partial cancellation detection (Apr 2026): new room-cancel detection, timestamp-gated global cancel, stored-status preservation for old partial cancels

## Prioritized Backlog

### P1 (High)
- None critical at this time

### P2 (Medium)
- ~~Encrypt users and bookings collections to 100%~~ DONE

### P3 (Low)
- Rate Manager quick toggle (Exely/HotelRunner)
- Legacy HR v1 connector removal (after full verification)
- Channel Manager Dashboard — recent reservations, failed imports, connection health metrics
- Admin UI Panel for encryption management (view status, trigger migrations, check audit logs)

## Completed Refactoring
- ~~hotelrunner_webhook.py monolith split~~ DONE (Apr 2026) — Split 1162-line file into hotelrunner_shared.py + hotelrunner_webhook.py + hotelrunner_sync.py

## Key API Endpoints
- GET /api/security/pii/strict-mode/config
- GET /api/security/pii/strict-mode/violations
- GET /api/ops/field-encryption/status
- POST /api/ops/field-encryption/migrate-all
- POST /api/ops/field-encryption/migrate/{collection_name}
- GET /api/ops/field-encryption/progress
- POST /api/channel-manager/hotelrunner/sync/reservations/pull
- GET /api/channel-manager/hotelrunner/sync/status
- POST /api/channel-manager/hotelrunner/webhooks/reservations

## 3rd Party Integrations
- AWS KMS (Encryption) — optional for production key management
- HotelRunner v2 — User Token active, LIVE MODE
- Exely (SOAP) — Provider credentials required

## Critical Constraints
- All responses in Turkish
- Latest test report: /app/test_reports/iteration_181.json
