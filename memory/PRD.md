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

### P3 - Security & Compliance (P0 ITEMS COMPLETED)
- [x] AWS KMS envelope encryption provider
- [x] Secret classification system (7 types with lifecycle rules)
- [x] PII Registry (31 fields, 4 categories, role-based masking)
- [x] PII masking for logs (SanitizedLogFilter on root logger)
- [x] PII masking for ops/timeline/raw-payload endpoints
- [x] PII access audit trail (MongoDB-backed, 180-day TTL)
- [x] PII anomaly detection
- [x] Secret inventory and classification API
- [ ] P1: API response role-based masking (guest endpoints, export/report)
- [ ] P1: Rotation script + rollback flow
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
