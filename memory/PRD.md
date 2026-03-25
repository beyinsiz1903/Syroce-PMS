# PMS (Property Management System) - PRD

## Original Problem Statement
Hotel Property Management System - full-stack application with React frontend and FastAPI backend with MongoDB. Multi-tenant PMS with booking management, room management, guest profiles, channel manager integration, enterprise features.

## User Personas
- Hotel managers and staff who manage bookings, rooms, guests, and operations.

## Project Priorities (User-Defined)

### P0 - Go-Live Hardening COMPLETED
- Vite production build optimized
- Nginx hardened
- Go-Live Runbook, SLO/SLA, Incident Playbook created

### P1 - Critical Fixes & Improvements COMPLETED
- `room-move-history` endpoint bug fix — schema normalized to canonical fields
- Load test suite expanded — multi-tenant, failure injection, retry storm, queue backlog, reconciliation
- Import boundary violations resolved — 3/3 exceptions eliminated
- CI orphan file guard fix — `create_test_user.py` moved to `scripts/`

### P2 - Code Quality & Hardening COMPLETED
- [x] CI Load Test Integration — 11 curated load tests as CI hard gate
- [x] Ruff UP Rules (safe wave) — UP006, UP012, UP015, UP017, UP024, UP034, UP041, UP045
- [ ] Ruff UP Rules (wave 2) — UP035 (deprecated imports), UP042 (StrEnum)
- [ ] App.jsx decomposition

### P3 - Security & Compliance
- [x] AWS KMS envelope encryption provider
- [x] Secret classification system (7 types with lifecycle rules)
- [x] PII Registry (31 fields, 4 categories, role-based masking)
- [x] PII masking for logs (SanitizedLogFilter on root logger)
- [x] PII masking for ops/timeline/raw-payload endpoints
- [x] PII access audit trail (MongoDB-backed, 180-day TTL)
- [x] PII anomaly detection
- [x] Secret inventory and classification API
- [x] **P1: Secret Rotation + Rollback Flow (COMPLETED 2026-03-25)**
- [x] **P1: Rotation Ops Panel Frontend (COMPLETED 2026-03-25)**
- [x] **P2: At-Rest PII Field Encryption — Faz 1 (COMPLETED 2026-03-25)**
  - FieldEncryptionService: AES-256-GCM encrypt/decrypt with HMAC-SHA256 search hashes
  - Encrypted write + dual read (plaintext compat during migration)
  - Hash indexes (_hash_email, _hash_phone, etc.) for exact-match search
  - Migration API: batch encrypt existing plaintext documents
  - Status/Progress/Audit endpoints for operational visibility
  - Frontend FieldEncryptionPanel: coverage bars, migrate buttons, audit trail
  - guests collection: 268/268 docs encrypted (100% coverage)
  - Testing: iteration_161 — 100% backend + 100% frontend pass
- [ ] P2 Faz 2: Migration for users/bookings collections + progress dashboard
- [ ] P2 Faz 3: Plaintext cleanup + mandatory encrypted-only mode
- [ ] P1: API response role-based masking (guest endpoints, export/report)

### Backlog
- Wire failure tracking into import bridge, outbox worker, ARI push engine
- Legacy DB import migration (~264 imports)
- Legacy collection cleanup (~489 collections)
- Motor -> pymongo async migration
- HMR guard decommission
- Configure Slack webhook for production alerts
- App.jsx decomposition

## Architecture
- Frontend: React + Vite + Shadcn UI
- Backend: FastAPI + Motor (async MongoDB)
- Database: MongoDB (hotel_pms)
- CI/CD: GitHub Actions

## What's Been Implemented
- Full PMS functionality (bookings, rooms, guests, housekeeping, etc.)
- Channel manager integrations (Exely, Booking.com adapter)
- Enterprise features (analytics, reports, revenue management)
- Go-Live Hardening (P0) - completed
- All P1 critical fixes and improvements - completed
- Comprehensive load test suite (5 files, 32 tests, 11 CI-gated)
- Clean import boundaries with zero violations
- CI guards: orphan files + import boundaries + load tests
- **AWS KMS / PII Masking (P0 items)**
- **Secret Rotation + Rollback System (P1 item, 2026-03-25)**
- **Rotation Ops Panel Frontend (2026-03-25)**
- **At-Rest PII Field Encryption — Faz 1 (2026-03-25):**
  - FieldEncryptionService: encrypt/decrypt/migrate/search for PII fields
  - AES-256-GCM encryption with aes256gcm: envelope format
  - HMAC-SHA256 search hashes with dedicated pepper
  - Dual-read: encrypted values decrypted, plaintext returned as-is
  - Hash indexes on 15 fields across 4 collections
  - Migration API: batch processing with progress tracking and audit trail
  - Frontend FieldEncryptionPanel with coverage bars, migrate buttons, audit
  - Guest CRUD fully integrated: encrypt on write, decrypt on read, hash search
  - Guests: 268/268 encrypted (100%), Users: 0/154, Bookings: 0/3100

## Key Files
- Backend entry: `/app/backend/server.py`
- Frontend entry: `/app/frontend/src/App.jsx`
- Routers: `/app/backend/routers/`
- Load tests: `/app/backend/load_tests/`
- CI scripts: `/app/backend/scripts/`
- Docs: `/app/docs/`
- CI: `/.github/workflows/ci-cd.yml`
- **Security:**
  - PII Registry: `/app/backend/security/pii_registry.py`
  - PII Audit: `/app/backend/security/pii_audit.py`
  - Classification Router: `/app/backend/security/classification_router.py`
  - Log Sanitizer: `/app/backend/security/log_sanitizer.py`
  - Sensitive Output: `/app/backend/security/sensitive_output.py`
  - KMS Provider: `/app/backend/core/crypto/kms_provider.py`
  - PII Masking Context: `/app/backend/security/pii_masking_middleware.py`
  - Rotation Engine: `/app/backend/security/rotation_engine.py`
  - Rotation Router: `/app/backend/security/rotation_router.py`
  - Rotation Ops Panel: `/app/frontend/src/components/RotationOpsPanel.jsx`
  - **Field Encryption Service: `/app/backend/security/field_encryption.py`**
  - **Field Encryption Router: `/app/backend/security/field_encryption_router.py`**
  - **Field Encryption Panel: `/app/frontend/src/components/FieldEncryptionPanel.jsx`**
  - **Guest Router (encrypted): `/app/backend/routers/pms_guests.py`**

## DB Collections (Security)
- `secret_rotation_versions` — Version history with encrypted payloads and status
- `secret_rotation_audit` — Rotation audit trail (1-year TTL)
- `secret_access_audit` — General secret access audit (90-day TTL)
- `pii_access_audit` — PII field access audit (180-day TTL)
- `_dev_secrets` — Live secret store (local dev backend)
- `field_encryption_progress` — Migration progress per collection
- `field_encryption_audit` — Field encryption operation audit trail

## Test Credentials
- Email: demo@hotel.com / Password: demo123

## Key Decisions
- BlockStatus/BlockType enums moved to `models/enums.py` (shared)
- BookingAdapter moved to `integrations/booking_adapter.py` (canonical location)
- Worker health exposed via `core/worker_health.py` facade (layer boundary)
- Room move history uses canonical fields: from_room_number, to_room_number, moved_at
- CI load tests use `@pytest.mark.ci_load` marker for selective execution
- Ruff UP rules applied in safe wave first, noisy rules deferred
- **PII masking uses application-layer approach (not middleware) to avoid GZip compression conflicts**
- **Passwords are NEVER unmaskable regardless of role**
- **AWS KMS envelope encryption (KMS1: format) for production key management**
- **Log sanitization auto-attached to root logger via SanitizedLogFilter**
- **Rotation uses system DB (`get_system_db()`) to bypass tenant isolation — ops-level operation**
- **Activation writes live secret FIRST, then updates version status (transactional safety)**
- **Version must pass test before activation — untested versions are blocked**
- **Field encryption uses AES-256-GCM (aes256gcm: format) via existing CredentialEncryptionService**
- **HMAC-SHA256 with dedicated pepper for deterministic search hashes**
- **Dual-read pattern: encrypted → decrypt, plaintext → return as-is (migration compat)**
- **Hash indexes stored as `_hash_{field}` alongside encrypted fields, sparse index**
- **Migration is batch-based with progress tracking and audit trail**
- **Encrypted documents marked with `_enc_version: 1` and `_encrypted_at` timestamp**
