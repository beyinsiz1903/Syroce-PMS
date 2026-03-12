# Syroce PMS - Product Requirements Document

## Original Problem Statement
Enterprise-grade cloud PMS (Property Management System) for hospitality operations. Multi-tenant, AI-powered hotel management platform built with React + FastAPI + MongoDB.

## Core Requirements
- Full PMS lifecycle: reservations, front desk, billing, housekeeping, night audit
- Multi-property management
- Channel manager integration
- Role-based access control (RBAC)
- Comprehensive audit trails
- Real-time operational dashboard

---

## What's Been Implemented

### Phase 1: PMS Core Hardening (Completed)
1. Reservation State Machine - Robust state transitions, duplicate protection, availability recalculation
2. Front Desk Workflow - Check-in/out, room moves, walk-ins, payment/folio dependencies
3. Folio/Billing Core - Charge/payment posting, refunds, split folios, tax calculations, transaction auditing
4. Housekeeping State Machine - Room status model (Clean, Dirty, Inspected, OOO/OOS)
5. Night Audit Engine - Business date roll, charge posting, exception handling
6. Role/Permission RBAC - Front Desk, Housekeeping, Finance permissions with supervisor overrides
7. PMS Operational Dashboard - KPI cards, room status, arrivals/departures
8. Tests: 53 unit tests + 25 API tests (100% pass)

### Phase 2: Operational Enhancement (Completed - March 2026)
1. **Folio Detail View** - Timeline with running balance, charge/payment/refund/void lines, tax breakdown per line, split folio visibility, city ledger transfer history, invoice association, audit trail, supervisor override & void reason visibility
2. **Dashboard Trend Graphs + Date Range Filters** - 7 trend graphs (arrivals, departures, occupancy, HK readiness, folio issues, audit exceptions, blocked check-ins) with date range filters (today/7d/30d/custom)
3. **Multi-Property Night Audit Coordination** - Property-based audit status board, completed/running/blocked/failed states, exception summary, unresolved blocker list, escalation flow, readiness score
4. **Auto Housekeeping Task Assignment** - Post-checkout auto task creation, VIP/early check-in priority, maintenance conflict check, floor attendant workload balancing, room readiness ETA, suggestion engine, manual override with reason
5. **Tests**: 26 unit tests + 22 API tests (100% pass)

---

## Architecture

### Backend Services (modules/pms_core/)
- `reservation_state_machine.py` - Reservation lifecycle
- `front_desk_service.py` - Front desk operations
- `folio_hardening_service.py` - Billing/folio operations
- `housekeeping_state_service.py` - Housekeeping state management
- `night_audit_engine.py` - Night audit process
- `role_permission_service.py` - RBAC
- `pms_dashboard_service.py` - Dashboard data
- `folio_detail_service.py` - Folio detail view (Phase 2)
- `dashboard_trends_service.py` - Trend graphs data (Phase 2)
- `multi_property_audit_service.py` - Multi-property audit (Phase 2)
- `auto_housekeeping_service.py` - Auto HK assignment (Phase 2)

### API Router
- `routers/pms_hardening.py` - All PMS endpoints under /api/pms-core/

### Frontend Pages
- `PMSOperationalDashboard.js` - Main dashboard with 6 tabs
- `FolioDetailView.js` - Folio detail page

---

## Prioritized Backlog

### P1 - Next
- UI/UX Polish: Interactive charts, advanced filtering
- Revenue Management: Rate optimization, yield management

### P2 - Future
- Expand Audit Trails: More granular action logging
- Guest Communication: Email/SMS integration
- Mobile front desk workflow
- Advanced reporting and analytics
