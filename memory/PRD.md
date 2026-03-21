# Syroce PMS — Product Requirements Document

## Overview
Enterprise-grade hospitality SaaS platform (Property Management System) for multi-hotel operations.

## Core Requirements
- Multi-tenant architecture with strict data isolation
- Real-time booking management with overbooking prevention
- Channel manager integration (Exely, HotelRunner)
- Front desk operations (check-in, check-out, walk-in, room moves)
- Folio management and payment tracking
- Housekeeping task management
- Night audit automation
- Guest journey management
- Reporting and analytics

## Architecture
```
/app
├── backend/
│   ├── core/
│   │   ├── atomic_booking.py          # Atomic booking creation (BOOK-001)
│   │   ├── atomic_checkin_checkout.py  # Atomic check-in/out (BOOK-002)
│   │   ├── tenant_db.py               # Tenant-scoped DB proxy (TI-001)
│   │   ├── database.py                # MongoDB connection (replica set)
│   │   └── security.py
│   ├── domains/                        # Business domains
│   ├── modules/                        # Service modules
│   ├── routers/                        # API routers
│   ├── startup.py                      # Indexes + lifecycle
│   └── tests/
├── frontend/                           # React SPA
└── GO_LIVE_EXECUTION_BLUEPRINT.md      # Full engineering plan
```

## Technical Stack
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (replica set for transactions)
- **Cache**: Redis (optional)
- **Frontend**: React

## Test Credentials
| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | demo@hotel.com | demo123 | super_admin |

## Key Data Models
- **bookings**: tenant_id, room_id, guest_id, status, check_in, check_out
- **rooms**: tenant_id, room_number, status, room_type
- **guests**: tenant_id, name, email, phone
- **folios**: tenant_id, booking_id, status, balance
- **outbox_events**: event_type, status, payload (event sourcing)
