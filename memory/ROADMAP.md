# ROADMAP

## P0 — Complete
- [x] HotelRunner REST adapter (production-grade)
- [x] Exely SOAP adapter (production-grade)
- [x] Real Exely test environment integration
- [x] Encrypted credential vault for provider secrets
- [x] CI pipeline test stability

## P1 — Next Up
- [ ] Mapping UI Improvement: PMS room/rate ↔ Provider room/rate mapping interface
- [ ] Test booking creation via Exely booking link + OTA_ReadRQ verification
- [ ] Reservation lineage: duplicate/stale detection

## P2 — Planned
- [ ] Legacy collection cleanup: archive unused DB collections
- [ ] Deprecation cleanup: remove exely_client_legacy.py, old hotelrunner.py
- [ ] Multi-day ARI push: date range, availability, restrictions, multi-day rate

## P3 — Backlog
- [ ] Service Wiring: Router → Service → Repository pattern (FrontDesk, NightAudit, Pricing, Mobile, Messaging)
- [ ] Schema Completion: inline models → shared schemas
- [ ] Frontend Role-Based Views: GM, Admin, Superadmin dashboards
- [ ] Frontend Stabilization: dependency audit, code splitting, error boundaries
- [ ] Stress Testing: 24h soak test, reservation burst, ARI storm
- [ ] HotelRunner real credential integration (when credentials available)
- [ ] Two-provider reconciliation verification
