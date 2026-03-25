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
  - Safe rotation: initiate → test → activate
  - Version history with full audit trail
  - Rollback to any previous version (single command)
  - Connector-based dry-run testing (Exely, HotelRunner)
  - Alert integration on rotation failure/rollback
  - Expiration tracking with overdue/warning dashboard
  - 8 new API endpoints, 21/21 tests passed
- [x] **P1: Rotation Ops Panel Frontend (COMPLETED 2026-03-25)**
  - Risk Summary Cards: overdue, warning, 7-day rollback, test failures, riskiest connector
  - Rotation Dashboard table: status, connector, secret path, active version, last rotated, next due, age bar
  - Audit Trail with expand/collapse (51 entries)
  - Secret Detail Sheet: status overview, timeline, version history, action buttons
  - Confirm dialogs for activate/rollback/test (safety controls)
  - Column sorting (status, connector, age)
  - All Turkish labels, dark theme, data-testid coverage
  - Testing: iteration_160 — 100% backend + 100% frontend pass
- [ ] P1: API response role-based masking (guest endpoints, export/report)
- [ ] P2: At-rest encryption for critical PII fields (phone, email, passport)

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
- Ruff UP safe auto-fix across entire codebase
- **AWS KMS / PII Masking (P0 items):**
  - PII Registry with 31 fields across 4 categories (identity, contact, financial, authentication)
  - Role-based masking (super_admin sees all, admin sees contact, others see masked)
  - AWS KMS envelope encryption provider (KMS1: format)
  - Secret classification (7 types: jwt_app, connector, webhook, encryption, third_party, database, internal)
  - Log sanitization filter (SanitizedLogFilter) on all handlers
  - PII audit trail with MongoDB indexes and 180-day TTL
  - PII anomaly detection for excessive unmask patterns
  - 8 new API endpoints for security operations
- **Secret Rotation + Rollback System (P1 item, 2026-03-25):**
  - Rotation Engine: initiate → dry-run test → activate → rollback
  - Version management: auto-incrementing versions, status tracking (pending_test → test_passed → active → archived → rolled_back)
  - Connector-specific testing: Exely (api_key + hotel_id), HotelRunner (token validation)
  - Rollback: instant restore to any previous version
  - Alert integration: fires on rotation failure (severity=high) and rollback (severity=warning)
  - Expiration dashboard: overdue/warning/healthy status per secret
  - Full audit trail: every rotation action logged with actor, timestamp, version
  - 8 new endpoints under /api/ops/secrets/rotation/
  - 21/21 tests passed (iteration 159)
- **Rotation Ops Panel Frontend (2026-03-25):**
  - Risk Summary Cards with 5 risk indicators
  - Rotation Dashboard table with status, connector, age, due dates
  - Audit Trail with 51+ entries and expand/collapse
  - Secret Detail Sheet with version history and action buttons
  - Confirm dialogs for critical operations (activate/rollback/test)
  - Column sorting, refresh, Turkish localization
  - Iteration 160: 100% backend + 100% frontend tests passed

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
  - **Rotation Engine: `/app/backend/security/rotation_engine.py`**
  - **Rotation Router: `/app/backend/security/rotation_router.py`**
  - **Rotation Ops Panel: `/app/frontend/src/components/RotationOpsPanel.jsx`**

## DB Collections (Security)
- `secret_rotation_versions` — Version history with encrypted payloads and status
- `secret_rotation_audit` — Rotation audit trail (1-year TTL)
- `secret_access_audit` — General secret access audit (90-day TTL)
- `pii_access_audit` — PII field access audit (180-day TTL)
- `_dev_secrets` — Live secret store (local dev backend)

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
