# Syroce PMS — Product Requirements Document

## Original Problem Statement
Cloud PMS + Channel Manager entegrasyon platformu. PMS çekirdeğini production-grade seviyeye çıkarmak.

## Core Architecture
- **Backend**: FastAPI + MongoDB (async)
- **Frontend**: React + Shadcn/UI + TailwindCSS
- **Auth**: JWT-based custom auth
- **Real-time**: WebSocket for admin dashboard

## What's Been Implemented

### Phase 1: Channel Manager & Production Validation (DONE)
- HotelRunner sandbox integration
- Reservation import/export
- Inventory sync engine
- Connector health monitoring
- Alert delivery system
- Production readiness checklist
- Mapping completeness validation
- Rate push tracking
- WebSocket real-time updates
- Health trend analytics

### Phase 2: PMS Core Hardening (DONE - 2026-03-12)
8-point production hardening plan fully implemented:

1. **Reservation State Machine** - Valid transitions enforced (pending→confirmed→checked_in→checked_out). Terminal states (cancelled, no_show, checked_out) reject further transitions. Overbooking prevention. Duplicate reservation detection.
2. **Front Desk Workflow** - Check-in with room readiness validation, checkout with folio balance check, room move for checked-in guests, walk-in with immediate check-in, early check-in/late checkout, room upgrade with rate adjustment.
3. **Folio/Billing Hardening** - Charge posting, payment posting, refund handling, split folio, tax breakdown, city ledger transfer, void/reversal with mandatory reason, transaction audit trail.
4. **Housekeeping State Machine** - Room status transitions (available→occupied→dirty→cleaning→inspected→available), inspection approval/rejection, room readiness blocker, maintenance impact analysis.
5. **Night Audit Engine** - Business date roll, room charge posting, pending arrival/departure control, no-show processing, unbalanced folio detection, tax consistency checks, daily audit snapshot, exceptions queue.
6. **Role/Permission RBAC** - Permission enforcement per operation, supervisor override detection, per-role permission listing.
7. **PMS Operational Dashboard** - Arrivals/departures today, in-house guests, room status summary, pending folio issues, audit exceptions, blocked check-ins.
8. **Comprehensive Testing** - 53 unit tests + 25 API tests, all passing.

## Key API Endpoints

### PMS Core (prefix: /api/pms-core)
- POST /check-in, /checkout, /walk-in, /cancel, /no-show
- POST /room-move, /room-upgrade, /late-checkout, /early-checkin
- GET /checkout-preview/{booking_id}, /overbooking-check
- POST /folio/charge, /folio/payment, /folio/refund
- POST /folio/void-charge, /folio/void-payment, /folio/split
- GET /folio/tax-breakdown/{folio_id}, /folio/audit/{folio_id}
- POST /folio/city-ledger-transfer
- POST /housekeeping/room-status, /housekeeping/inspection-approval
- GET /housekeeping/room-readiness/{room_id}, /housekeeping/room-summary
- GET /housekeeping/maintenance-impact
- POST /night-audit/run, /night-audit/resolve-exception
- GET /night-audit/business-date, /night-audit/exceptions, /night-audit/snapshot/{date}
- GET /dashboard/operational, /permissions/me, /audit-trail
- GET /reservation-audit/{booking_id}

## File Architecture (PMS Core)
```
backend/modules/pms_core/
├── __init__.py
├── reservation_state_machine.py
├── front_desk_service.py
├── folio_hardening_service.py
├── housekeeping_state_service.py
├── night_audit_engine.py
├── pms_dashboard_service.py
└── role_permission_service.py
backend/routers/pms_hardening.py
backend/tests/test_pms_hardening.py
backend/tests/test_pms_hardening_api.py
frontend/src/pages/PMSOperationalDashboard.js
```

## Test Credentials
| User | Email | Password |
|---|---|---|
| Demo Admin | demo@hotel.com | demo123 |

## Prioritized Backlog

### P1 - Next
- Interactive charts for operational dashboard
- Date range filters for audit trail
- Folio detailed view in dashboard

### P2 - Future
- Multi-property night audit coordination
- Automated housekeeping task assignment
- Revenue analytics integration
- Guest communication for check-in/checkout
- Mobile front desk workflow
