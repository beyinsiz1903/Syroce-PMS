# ROADMAP

## P0 — Go-Live Critical (14-Day War Plan)
- [ ] BOOK-001: Atomic availability check + booking create (Day 1)
- [ ] BOOK-002: MongoDB transactions for check-in/check-out (Day 2)
- [ ] TI-001: Tenant isolation enforcement middleware (Day 3)
- [ ] OTA-001: OTA → PMS automatic booking import (Day 4)
- [ ] OTA-002: PMS → OTA guaranteed delivery via outbox (Day 5)
- [ ] OTA-003: ARI push persistence (Day 6)
- [ ] NA-001 + NA-002: Night audit hardening (Day 7)
- [ ] OBS-001: Deep health checks + alerting (Day 8)
- [ ] PERF-001: Compound indexes for hot queries (Day 1)
- [ ] Concurrency test suite (Day 9)
- [ ] E2E OTA sync test (Day 10)
- [ ] Night audit + financial reconciliation test (Day 11)
- [ ] Performance baseline (Day 12)
- [ ] Staging dry run (Day 13)
- [ ] Go/No-Go decision (Day 14)

## P0 — Complete (Previous)
- [x] HotelRunner REST adapter (production-grade)
- [x] Exely SOAP adapter (production-grade)
- [x] Real Exely test environment integration
- [x] Encrypted credential vault for provider secrets
- [x] CI pipeline test stability

## P1 — Complete
- [x] Mapping UI Improvement
- [x] Test booking creation + OTA_ReadRQ verification
- [x] Reservation lineage: duplicate/stale detection

## P2 — Post Go-Live
- [ ] pms.py decomposition (2714 lines)
- [ ] Collection registry (centralize db references)
- [ ] Legacy collection cleanup
- [ ] Deprecation cleanup (exely_client_legacy.py, old hotelrunner.py)
- [ ] Multi-day ARI push

## P3 — Backlog
- [ ] Service Wiring: Router → Service → Repository pattern
- [ ] Schema Completion: inline models → shared schemas
- [ ] Frontend Role-Based Views
- [ ] Frontend Stabilization
- [ ] Stress Testing (24h soak)
- [ ] HotelRunner real credential integration
- [ ] Two-provider reconciliation verification
