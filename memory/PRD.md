# Syroce PMS — Product Requirements Document

## Original Problem Statement
Build a production-safe, enterprise-grade hospitality SaaS platform (PMS) with reliable data flows, multi-tenant isolation, and auditable financial operations.

## Core System
- **Stack**: React frontend + FastAPI backend + MongoDB
- **Architecture**: Multi-tenant with tenant_id scoping, async Motor MongoDB, channel manager integrations (Exely, HotelRunner)

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Completed Features (Chronological)

### Phase 1: Core PMS
- Room management, booking lifecycle, guest management
- Folio management with charge posting
- Night audit (legacy version)
- Rate management, housekeeping, reporting
- Channel manager integration (Exely, HotelRunner)

### Phase 2: Production Hardening
- **TI-001 (Partial)**: Tenant isolation proof-of-concept (TenantScopedDB proxy in core/tenant_db.py)
- **Atomic Booking**: Transaction-safe booking creation
- **Atomic Check-in/Checkout**: Transaction-safe check-in and checkout
- **OTA Outbox Pattern**: Reliable outbound OTA sync with retry
- **Folio Hardening**: Validated charge posting with balance recalculation

### Phase 3: Data Integrity
- **DATA-001**: Guaranteed Inbound Booking Import Bridge (state-machine OTA→PMS import with retry worker)
- **NA-001/NA-002**: Night Audit Hardening (state-machine financial close engine)
  - Run-level orchestration with `night_audit_runs` collection
  - Item-level transactional posting with `night_audit_run_items` collection
  - Idempotent duplicate prevention via unique indexes on `folio_charges`
  - Business date roll ONLY after verified successful close
  - Stale run detection (15min heartbeat threshold), resume, abort
  - Admin endpoints: POST /run, GET /status, GET /runs, GET /items, POST /resume, POST /abort
  - Enhanced /health/deep with night audit metrics
  - 44 passing tests (23 unit + 21 API)

## Key Technical Patterns
- **State Machine**: Used for import bridge and night audit runs
- **Atomic Claims**: find_one_and_update for safe concurrent processing
- **Transactional Posting**: MongoDB transactions for financial operations
- **Idempotency**: Unique indexes prevent duplicate data
- **Background Workers**: AsyncIO tasks for retry/polling

## Pending Work
### P0
- **TI-003**: Integrate TenantScopedDB proxy across all service/router layers (security)

### P1
- Fix pre-existing test failures in test_hardening_comprehensive.py
- Fix lint errors in frontdesk_router.py and misc_router.py

### P2 (Backlog)
- Night Audit Hardening — Night audit schedule integration testing
- Data Model Repair (reduce collection sprawl)
- pms.py decomposition (2714 lines → modular services)
- OBS-002: Outbox Dashboard Metrics (frontend)
- Import Bridge Review Queue Dashboard (frontend)
- Night Audit Run Dashboard (frontend)
- Stress testing, security audit, PII masking
- Legacy collection cleanup
- Refactor @cached decorator
