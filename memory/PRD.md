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
- **TI-001**: Tenant isolation proof-of-concept (TenantScopedDB proxy)
- **TI-002**: Tenant isolation proof test suite (11 tests)
- **TI-003**: Tenant Isolation Full Enforcement (3-layer system)
  - Layer 1: TenantAwareDBProxy replaces raw `db` in core/database.py
  - Layer 2: Runtime Guard with STRICT_TENANT_MODE env flag
  - Layer 3: Static Audit via CI script (scripts/check_raw_db.py)
  - TenantContextMiddleware sets tenant from JWT on every request
  - LazyCollection descriptor for class-level repository access
  - 66 passing tests (35 unit + 31 API)
- **Atomic Booking**: Transaction-safe booking creation
- **Atomic Check-in/Checkout**: Transaction-safe check-in and checkout
- **OTA Outbox Pattern**: Reliable outbound OTA sync with retry
- **Folio Hardening**: Validated charge posting with balance recalculation

### Phase 3: Data Integrity
- **DATA-001**: Guaranteed Inbound Booking Import Bridge
- **NA-001/NA-002**: Night Audit Hardening (state-machine financial close engine)
  - 44 passing tests (23 unit + 21 API)

## Key Technical Patterns
- **TenantAwareDBProxy**: Transparent proxy on `db` object — auto-scopes queries from contextvars
- **TenantContextMiddleware**: Extracts tenant_id from JWT, sets it in contextvars per-request
- **LazyCollection**: Descriptor for repository classes that resolves collection through proxy at access time
- **State Machine**: Used for import bridge and night audit runs
- **Atomic Claims**: find_one_and_update for safe concurrent processing
- **Transactional Posting**: MongoDB transactions for financial operations
- **Idempotency**: Unique indexes prevent duplicate data

## Pending Work
### P1
- Gradual migration: Replace `from core.database import db` with `get_db()` in 264 legacy files
- Fix pre-existing test failures in test_hardening_comprehensive.py
- Fix lint errors in frontdesk_router.py and misc_router.py
- Enable STRICT_TENANT_MODE once all files are migrated

### P2 (Backlog)
- Data Model Repair (reduce collection sprawl)
- pms.py decomposition (2714 lines → modular services)
- OBS-002: Outbox Dashboard Metrics (frontend)
- Import Bridge Review Queue Dashboard (frontend)
- Night Audit Run Dashboard (frontend)
- Stress testing, security audit, PII masking
- Legacy collection cleanup
- Refactor @cached decorator
