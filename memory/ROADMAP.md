# ROADMAP

## P0 — Remaining Service Wiring
- [ ] Extract business logic from frontdesk_router.py to FrontDeskService
- [ ] Extract business logic from night_audit_router.py to NightAuditService
- [ ] Extract business logic from pricing_router.py to PricingService
- [ ] Extract business logic from mobile_router.py to MobileService
- [ ] Create MessagingService from guest/messaging/router.py
- [ ] Establish router → service → repository pattern for remaining routers

## P1 — Schema Completion
- [ ] Extract remaining inline models from pos_fnb_router.py, rms_router.py
- [ ] Create shared schemas for cross-domain models (pagination, audit context)
- [ ] Add response model type annotations to all endpoints

## P1 — Frontend Role-Based Views
- [ ] GM: property-level summary in SystemHealthDashboard
- [ ] Admin: tenant/property scoped operational summary
- [ ] Superadmin: cross-property/global summary
- [ ] Live refresh support (polling/WebSocket)

## P2 — Frontend Stabilization
- [ ] Audit frontend dependencies
- [ ] Implement route-based code splitting
- [ ] Error boundary components for runtime panels

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
