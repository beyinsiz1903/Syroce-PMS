# Syroce PMS — Changelog

## [2026-03-25] AWS KMS + PII Masking + Secret Classification (P3 Security)
- Implemented PII Registry with 31 field definitions across 4 categories (identity, contact, financial, authentication)
  - Role-based masking: super_admin sees all, admin sees contact info, others see masked data
  - Passwords ALWAYS masked regardless of role
  - 4 masking levels: full, partial, hash, none
- AWS KMS Envelope Encryption provider (`KMS1:` format)
  - Uses KMS GenerateDataKey for envelope encryption
  - AES-256-GCM local encryption with KMS-managed data keys
  - Gracefully reports unavailable when AWS_KMS_KEY_ARN not configured
- Secret Classification system with 7 types and lifecycle rules
  - jwt_app, connector, webhook, encryption, third_party, database, internal
  - Each type has rotation_max_days, rotation_warning_days, auto_rotation flags
- Enhanced Log Sanitizer with SanitizedLogFilter
  - Auto-attached to root logger handlers on startup
  - Expanded regex patterns (email, phone, cards, JWT, AWS keys, MongoDB URIs, etc.)
  - Fixed false positives: UUID patterns no longer matched as phone numbers
- PII Access Audit trail (MongoDB collection: pii_access_audit, 180-day TTL)
- PII Anomaly detection for excessive unmask patterns
- 8 new API endpoints under /api/ops/:
  - GET /api/ops/pii/policy, /audit, /anomalies, /metrics
  - GET /api/ops/secrets/classification, /inventory
  - GET /api/ops/kms/status
- Raw webhook payload PII masking in timeline router
- Testing: 20/20 tests passed (iteration_158)

## [2026-03-25] CI Load Test Integration + Ruff UP Auto-fix (P2)
- Integrated 11 curated load tests into CI pipeline as a hard gate job
  - New `load-test` job in `ci-cd.yml` with MongoDB + Redis services
  - `@pytest.mark.ci_load` marker on 11 tests across 5 load test files
  - `docker-build` now depends on `load-test` — deploys blocked if load tests fail
  - Covers: availability consistency, concurrent bookings, dashboard reads, retry storms, multi-tenant isolation, failure recovery
- Applied Ruff `UP` safe auto-fix rules across entire backend codebase
  - Enabled rules: UP006, UP012, UP015, UP017, UP024, UP034, UP041, UP045
  - 8294+ automatic fixes applied (modern Python 3.11 syntax)
  - All existing ruff checks continue to pass
- Fixed 3 pre-existing bugs in load tests:
  - Health endpoint path: `/api/health/` → `/health/`
  - Invalid UserRole: `"manager"` → `"admin"`
  - Missing Tenant `property_name` field in multi-tenant fixture
- Testing: 11/11 CI load tests pass, 11/11 verification tests pass

## [2026-02-25] Go-Live Hardening (P0)
- Vite prod build optimized: chunk splitting (vendor-react 219KB, vendor-charts 406KB, vendor-ui 36KB), sourcemap off, es2020 target, 6.9MB total
- Nginx container config hardened: gzip level 6, security headers, immutable asset caching, proxy buffering, dot-file blocking
- Created Go-Live Runbook: 8-section operational deploy procedure with rollback matrix
- Created SLO/SLA: 3-tier model with error budget policy and customer SLA tiers
- Created Incident Playbook: SEV classification, response procedures, 5 scenario runbooks, post-mortem template
- Fixed CI: Restored `create_test_user.py` to backend root (CI seed gate was failing)
- Fixed 4 Ruff lint errors: unused imports in pms_bookings, pms_dashboard, pms_room_queue

## [2026-02-25] pms.py Stage 3 Decomposition (P0)
- Load & Chaos Testing Framework: 18 tests (availability, booking, mutation concurrency)
- Fixed 2 ObjectId serialization bugs in allotment_contracts and group_reservations
- Extracted: pms_services, pms_room_queue, pms_room_details, pms_reservations, pms_availability
- pms.py reduced from 1384 to 21 lines (backward-compat placeholder)
- 116/116 tests pass (59 wiring + 39 functional + 18 load)

## [Previous] Stage 2 Decomposition
- Extracted pms_bookings.py (10 routes), pms_dashboard.py (3 routes)
- Created pms_shared.py for pure helpers
- pms.py reduced from 2934 to 1384 lines

## [Previous] Stage 1
- Room and guest modules extracted
- CI/CD pipeline with sandbox regression gate
- Tenant isolation middleware
