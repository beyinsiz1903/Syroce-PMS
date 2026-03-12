# ROADMAP

## P0 — Domain Service Wiring
- [ ] Extract business logic from router files into service layer
- [ ] Create: RoomService, ReservationService, FolioService, HousekeepingService
- [ ] Create: InventorySyncService, ReservationImportService, PricingService, MessagingService
- [ ] Establish router → service → repository pattern
- [ ] Ensure FastAPI dependency does not leak into service layer

## P1 — Schema Organization
- [ ] Create `backend/schemas/` directory with domain-organized files
- [ ] Extract inline Pydantic models from domain routers to schemas
- [ ] Establish clear schema ownership per domain

## P2 — Frontend Stabilization
- [ ] Audit frontend dependencies
- [ ] Implement route-based code splitting
- [ ] Frontend rendering of new hardening status dashboards

## P3 — Operational Reliability Tests
- [ ] Runtime stress tests: OTA reservation burst
- [ ] ARI update storm simulation
- [ ] Worker queue saturation test
- [ ] Reconciliation under drift storm
- [ ] Tenant isolation failure test

## P3 — PMS Load Test Framework
- [ ] k6/Locust scripts for key flows
- [ ] Baseline performance metrics
- [ ] CI-integrated load test execution
