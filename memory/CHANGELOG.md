# Syroce PMS — Changelog

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
