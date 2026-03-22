# Syroce PMS — Roadmap

## Completed (P0)
- [x] BOOK-001: Atomic Booking / Overbooking Prevention
- [x] BOOK-002: Atomic Check-in/Check-out Transactions
- [x] TI-001: Tenant Isolation Enforcement (TenantScopedDB)
- [x] TI-002: Tenant Isolation Proof Test Suite
- [x] TI-003: Tenant Isolation Full Enforcement (3-layer: Proxy + Runtime + Static)
- [x] PERF-001: Compound Indexes for Hot Queries
- [x] OBS-001: Deep Health Check Endpoint
- [x] OTA-002: PMS → OTA Guaranteed Delivery (Outbox Pattern)
- [x] DATA-001: OTA → PMS Automatic Booking Import Reliability
- [x] NA-001: Night Audit Hardening — Folio validation before charge posting
- [x] NA-002: Night Audit Hardening — Transactional charge posting

## Next Up (P1)
- [ ] TI-003b: Gradual migration of 264 legacy files to get_db() pattern
- [ ] TI-003c: Enable STRICT_TENANT_MODE after full migration
- [ ] Fix pre-existing test failures (test_hardening_comprehensive.py)
- [ ] Fix lint errors in frontdesk_router.py and misc_router.py

## P1 — Architecture
- [ ] INFRA-002: Collection Registry (centralize db references)
- [ ] PERF-002: Availability Query Optimization (aggregation pipeline)
- [ ] SEC-001: PII Masking in Logs
- [ ] pms.py decomposition (2714 lines → modular services)

## P2 — Technical Debt
- [ ] Legacy collection cleanup (~489 collections)
- [ ] Refactor @cached decorator (cache_manager.py)
- [ ] Frontend role-based views
- [ ] Data Model Repair Plan (reduce collection sprawl)

## Future
- [ ] Stress testing
- [ ] Security audit & dependency updates
- [ ] OBS-002: Outbox Dashboard Metrics
- [ ] Import Bridge Review Queue Dashboard (frontend)
- [ ] Night Audit Run Dashboard (frontend)
- [ ] Two-provider reconciliation verification
